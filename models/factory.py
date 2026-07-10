import os


def list_models():
    return ["unet3d", "sdf_refine_unet", "sam_med3d"]


def create_model(model_name, **kwargs):
    name = str(model_name).lower()
    if name == "unet3d":
        from .unet3d import UNet3D

        return UNet3D(
            in_channels=kwargs.get("in_channels", 1),
            out_channels=kwargs.get("out_channels", kwargs.get("n_classes", 1)),
            base_filters=kwargs.get("base_filters", 16),
        )
    if name in ("sdf_refine", "sdf_refine_unet"):
        from .sdf_refine_net import SDFRefineNet

        return SDFRefineNet(
            in_channels=kwargs.get("in_channels", 9),
            out_channels=kwargs.get("out_channels", 1),
            base_filters=kwargs.get("base_filters", 12),
        )
    if name in ("sam", "sam_med3d"):
        from .sam_med3d_adapter import SAMMed3DAdapter

        sam_root = kwargs.get("sam_root") or os.environ.get("SAM_MED3D_ROOT")
        checkpoint = kwargs.get("checkpoint") or os.environ.get("SAM_MED3D_CKPT")
        return SAMMed3DAdapter(
            sam_root=sam_root,
            checkpoint=checkpoint,
            model_type=kwargs.get("model_type", "vit_b_ori"),
            freeze_image_encoder=kwargs.get("freeze_image_encoder", True),
            freeze_prompt_encoder=kwargs.get("freeze_prompt_encoder", False),
            train_mask_decoder=kwargs.get("train_mask_decoder", True),
            intensity_min=kwargs.get("intensity_min", -1000.0),
            intensity_max=kwargs.get("intensity_max", 400.0),
        )
    raise ValueError(f"Unknown model_name={model_name!r}. Available: {', '.join(list_models())}")
