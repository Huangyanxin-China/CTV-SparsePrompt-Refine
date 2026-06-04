import argparse
import os
import sys

import torch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models import create_model, list_models


def check_unet_like(model_name, in_channels, shape, base_filters):
    model = create_model(model_name, in_channels=in_channels, base_filters=base_filters)
    model.eval()
    x = torch.randn(1, in_channels, *shape)
    with torch.no_grad():
        y = model(x)
    print(f"{model_name}: input={tuple(x.shape)} output={tuple(y.shape)}")


def check_sam(args):
    model = create_model(
        "sam_med3d",
        sam_root=args.sam_root,
        checkpoint=args.sam_checkpoint,
        model_type=args.sam_model_type,
        freeze_image_encoder=True,
        freeze_prompt_encoder=True,
        train_mask_decoder=False,
    )
    model.eval()
    d, h, w = args.sam_shape
    image = torch.randn(1, 1, d, h, w) * 250.0 - 500.0
    boxes = torch.tensor([[8.0, 8.0, 8.0, w - 8.0, h - 8.0, d - 8.0]])
    points = torch.tensor([[[w / 2.0, h / 2.0, d / 2.0]]])
    point_labels = torch.ones(1, 1, dtype=torch.long)
    with torch.no_grad():
        out = model(image, boxes=boxes, points=points, point_labels=point_labels)
    print(
        "sam_med3d:",
        f"input={tuple(image.shape)}",
        f"logits={tuple(out['logits'].shape)}",
        f"low_res={tuple(out['low_res_logits'].shape)}",
    )


def main():
    parser = argparse.ArgumentParser(description="Check model backbone construction and tensor shapes.")
    parser.add_argument("--models", nargs="+", default=["unet3d", "sdf_refine_unet"])
    parser.add_argument("--shape", type=int, nargs=3, default=[32, 32, 32])
    parser.add_argument("--base_filters", type=int, default=8)
    parser.add_argument("--sam_root", default="/share3/home/huangyanxin/SAM-Med3D-main")
    parser.add_argument("--sam_checkpoint", default="/share3/home/huangyanxin/SAM-Med3D-main/ckpt/sam_med3d_turbo.pth")
    parser.add_argument("--sam_model_type", default="vit_b_ori")
    parser.add_argument("--sam_shape", type=int, nargs=3, default=[64, 64, 64])
    args = parser.parse_args()

    print("Available models:", ", ".join(list_models()))
    for name in args.models:
        if name == "sam_med3d":
            check_sam(args)
        elif name == "unet3d":
            check_unet_like(name, in_channels=1, shape=args.shape, base_filters=args.base_filters)
        elif name in ("sdf_refine", "sdf_refine_unet"):
            check_unet_like("sdf_refine_unet", in_channels=8, shape=args.shape, base_filters=args.base_filters)
        else:
            raise ValueError(f"Unsupported check target: {name}")


if __name__ == "__main__":
    main()
