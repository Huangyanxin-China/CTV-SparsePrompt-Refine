#!/usr/bin/env python3
import argparse
import os
import os.path as osp
import sys
from glob import glob

from tqdm import tqdm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/share3/home/huangyanxin/SAM-Med3D-main")
    parser.add_argument("--img_dir", required=True)
    parser.add_argument("--gt_dir", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--num_clicks", type=int, default=10)
    parser.add_argument("--crop_size", type=int, default=128)
    parser.add_argument("--target_spacing", nargs=3, type=float, default=[1.5, 1.5, 1.5])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    sys.path.insert(0, repo)

    import medim
    from utils.infer_utils import validate_paired_img_gt

    os.makedirs(args.out_dir, exist_ok=True)
    model = medim.create_model("SAM-Med3D", pretrained=True, checkpoint_path=args.ckpt)

    gt_paths = sorted(glob(osp.join(args.gt_dir, "*.nii.gz")))
    if args.limit > 0:
        gt_paths = gt_paths[:args.limit]

    for gt_path in tqdm(gt_paths, desc="SAM-Med3D prompt inference"):
        case = osp.basename(gt_path).replace(".nii.gz", "")
        img_path = osp.join(args.img_dir, f"{case}_0000.nii.gz")
        if not osp.exists(img_path):
            raise FileNotFoundError(img_path)
        out_path = osp.join(args.out_dir, f"{case}.nii.gz")
        validate_paired_img_gt(
            model,
            img_path,
            gt_path,
            out_path,
            num_clicks=args.num_clicks,
            crop_size=args.crop_size,
            target_spacing=tuple(args.target_spacing),
        )


if __name__ == "__main__":
    main()
