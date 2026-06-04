#!/usr/bin/env python3
import argparse
import glob
import os
import sys


def clean_state_dict(sd):
    if "module" in sd and isinstance(sd["module"], dict):
        sd = sd["module"]
    return {
        (k[7:] if str(k).startswith("module.") else k): v
        for k, v in sd.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/share3/home/huangyanxin/DiffUNet-main")
    parser.add_argument("--data_dir", required=True)
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--out_channels", type=int, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--patch_size", nargs=3, type=int, default=[128, 128, 128])
    parser.add_argument("--sw_batch_size", type=int, default=2)
    parser.add_argument("--disable_tta", action="store_true")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    sys.path.insert(0, repo)

    import torch
    from monai.data import DataLoader
    from monai.inferers import SlidingWindowInferer

    from diffunet.diffunet_model import DiffUNet
    from light_training.dataloading.dataset import MedicalDataset
    from light_training.prediction import Predictor

    os.makedirs(args.out_dir, exist_ok=True)

    model = DiffUNet(1, args.out_channels)
    sd = torch.load(args.model_path, map_location="cpu")
    model.load_state_dict(clean_state_dict(sd), strict=True)
    model.eval()

    window_infer = SlidingWindowInferer(
        roi_size=args.patch_size,
        sw_batch_size=args.sw_batch_size,
        overlap=0.5,
        progress=True,
        mode="gaussian",
    )
    mirror_axes = None if args.disable_tta else [0, 1, 2]
    predictor = Predictor(window_infer=window_infer, mirror_axes=mirror_axes)

    paths = sorted(glob.glob(os.path.join(args.data_dir, "*.npz")))
    dataset = MedicalDataset(paths)
    loader = DataLoader(dataset, batch_size=1, shuffle=False, pin_memory=True)

    for batch in loader:
        image = batch["data"].float()
        properties = batch["properties"]
        output = predictor.maybe_mirror_and_predict(image, model, device=args.device)
        output = predictor.predict_raw_probability(output, properties=properties)
        output = output.argmax(dim=0)
        output = predictor.predict_noncrop_probability(output, properties)

        case_name = properties["name"][0]
        if case_name.endswith("_0000"):
            case_name = case_name[:-5]
        predictor.save_to_nii(
            output,
            raw_spacing=[1, 1, 1],
            case_name=case_name,
            save_dir=args.out_dir,
            postprocess=False,
        )


if __name__ == "__main__":
    main()
