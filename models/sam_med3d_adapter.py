import os
import sys

import torch
import torch.nn as nn
import torch.nn.functional as F


DEFAULT_SAM_ROOT = os.environ.get("SAM_MED3D_ROOT")
DEFAULT_SAM_CKPT = os.environ.get("SAM_MED3D_CKPT")


class SAMMed3DAdapter(nn.Module):
    """Thin adapter around the external SAM-Med3D implementation.

    This wrapper keeps the current project independent from the SAM-Med3D
    source tree while allowing controlled comparisons with UNet-style models.
    Input CT volumes are resized to SAM's fixed cubic input size, prompts are
    scaled consistently, and logits are returned in the original volume shape.
    """

    def __init__(
        self,
        sam_root=DEFAULT_SAM_ROOT,
        checkpoint=DEFAULT_SAM_CKPT,
        model_type="vit_b_ori",
        freeze_image_encoder=True,
        freeze_prompt_encoder=False,
        train_mask_decoder=True,
        intensity_min=-1000.0,
        intensity_max=400.0,
    ):
        super().__init__()
        self.sam_root = sam_root
        self.checkpoint = checkpoint
        self.model_type = model_type
        self.intensity_min = float(intensity_min)
        self.intensity_max = float(intensity_max)

        if not sam_root:
            raise ValueError("Set sam_root or SAM_MED3D_ROOT before creating SAMMed3DAdapter.")
        if not os.path.isdir(sam_root):
            raise FileNotFoundError(f"SAM-Med3D root not found: {sam_root}")
        if checkpoint and not os.path.exists(checkpoint):
            raise FileNotFoundError(f"SAM-Med3D checkpoint not found: {checkpoint}")
        if sam_root not in sys.path:
            sys.path.insert(0, sam_root)

        from segment_anything.build_sam3D import sam_model_registry3D

        self.sam = sam_model_registry3D[model_type](checkpoint=None)
        if checkpoint:
            try:
                state_dict = torch.load(checkpoint, map_location="cpu")
            except Exception:
                # SAM-Med3D public checkpoints may contain an argparse.Namespace
                # and require the pre-PyTorch-2.6 loading path. This is only
                # used for an explicitly configured local checkpoint.
                state_dict = torch.load(checkpoint, map_location="cpu", weights_only=False)
            if isinstance(state_dict, dict) and "model" in state_dict:
                state_dict = state_dict["model"]
            if isinstance(state_dict, dict) and "state_dict" in state_dict:
                state_dict = state_dict["state_dict"]
            if isinstance(state_dict, dict) and "model_state_dict" in state_dict:
                state_dict = state_dict["model_state_dict"]
            state_dict = {
                key.replace("module.", "", 1) if key.startswith("module.") else key: value
                for key, value in state_dict.items()
            }
            self.sam.load_state_dict(state_dict, strict=True)
        self.input_size = int(self.sam.image_encoder.img_size)
        self._set_trainable(self.sam.image_encoder, not freeze_image_encoder)
        self._set_trainable(self.sam.prompt_encoder, not freeze_prompt_encoder)
        self._set_trainable(self.sam.mask_decoder, bool(train_mask_decoder))

    @staticmethod
    def _set_trainable(module, trainable):
        for param in module.parameters():
            param.requires_grad = bool(trainable)

    def _normalize_ct(self, image):
        image = image.clamp(self.intensity_min, self.intensity_max)
        image = (image - self.intensity_min) / max(self.intensity_max - self.intensity_min, 1e-6)
        return image * 255.0

    def _scale_boxes(self, boxes, original_shape):
        if boxes is None:
            return None
        boxes = boxes.float()
        if boxes.ndim == 3 and boxes.shape[1] == 1:
            boxes = boxes[:, 0]
        if boxes.shape[-1] != 6:
            raise ValueError("boxes must have shape [B, 6] or [B, 1, 6] in x0,y0,z0,x1,y1,z1 order.")
        d, h, w = original_shape
        scale = boxes.new_tensor([
            self.input_size / max(w, 1),
            self.input_size / max(h, 1),
            self.input_size / max(d, 1),
            self.input_size / max(w, 1),
            self.input_size / max(h, 1),
            self.input_size / max(d, 1),
        ])
        return boxes * scale

    def _scale_points(self, points, original_shape):
        if points is None:
            return None
        d, h, w = original_shape
        scale = points.new_tensor([
            self.input_size / max(w, 1),
            self.input_size / max(h, 1),
            self.input_size / max(d, 1),
        ])
        return points.float() * scale

    def forward(self, image, boxes=None, points=None, point_labels=None, mask_inputs=None):
        """Return full-resolution logits.

        Args:
            image: [B, 1, D, H, W] CT volume in HU.
            boxes: optional [B, 6] or [B, 1, 6], x0,y0,z0,x1,y1,z1.
            points: optional [B, N, 3], x,y,z.
            point_labels: optional [B, N], 1 foreground and 0 background.
            mask_inputs: optional [B, 1, D, H, W] previous low-confidence mask.
        """
        if image.ndim != 5 or image.shape[1] != 1:
            raise ValueError("SAMMed3DAdapter expects image shape [B, 1, D, H, W].")
        original_shape = tuple(int(v) for v in image.shape[-3:])
        x = self._normalize_ct(image)
        if original_shape != (self.input_size, self.input_size, self.input_size):
            x = F.interpolate(
                x,
                size=(self.input_size, self.input_size, self.input_size),
                mode="trilinear",
                align_corners=False,
            )

        boxes_scaled = self._scale_boxes(boxes, original_shape)
        points_scaled = self._scale_points(points, original_shape)
        prompt_points = None
        if points_scaled is not None:
            if point_labels is None:
                point_labels = torch.ones(points_scaled.shape[:2], device=points_scaled.device, dtype=torch.long)
            prompt_points = (points_scaled, point_labels.to(points_scaled.device))

        if mask_inputs is not None:
            mask_inputs = F.interpolate(
                mask_inputs.float(),
                size=(self.input_size // 4, self.input_size // 4, self.input_size // 4),
                mode="trilinear",
                align_corners=False,
            )

        if all(not p.requires_grad for p in self.sam.image_encoder.parameters()):
            with torch.no_grad():
                image_embeddings = self.sam.image_encoder(x)
        else:
            image_embeddings = self.sam.image_encoder(x)
        sparse_embeddings, dense_embeddings = self.sam.prompt_encoder(
            points=prompt_points,
            boxes=boxes_scaled,
            masks=mask_inputs,
        )
        low_res_logits, iou_predictions = self.sam.mask_decoder(
            image_embeddings=image_embeddings,
            image_pe=self.sam.prompt_encoder.get_dense_pe(),
            sparse_prompt_embeddings=sparse_embeddings,
            dense_prompt_embeddings=dense_embeddings,
            multimask_output=False,
        )
        logits = F.interpolate(low_res_logits, size=original_shape, mode="trilinear", align_corners=False)
        return {"logits": logits, "low_res_logits": low_res_logits, "iou_predictions": iou_predictions}
