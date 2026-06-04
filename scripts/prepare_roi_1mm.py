#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import os
import sys

import pandas as pd
import SimpleITK as sitk
from tqdm import tqdm

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.io import ensure_dir, resample_to_spacing


def resolve_source_path(path, source_root):
    if os.path.isabs(str(path)):
        return str(path)
    return os.path.join(source_root, str(path))


def main():
    parser = argparse.ArgumentParser(description="Resample ROI images/labels to 1mm isotropic spacing.")
    parser.add_argument("--source_csv", default="/share3/home/huangyanxin/Seg4TV/data/train_with_roi.csv")
    parser.add_argument("--output_csv", default="data/roi_1mm/roi_1mm.csv")
    parser.add_argument("--image_dir", default="data/roi_1mm/images")
    parser.add_argument("--label_dir", default="data/roi_1mm/labels")
    parser.add_argument("--spacing", type=float, nargs=3, default=[1.0, 1.0, 1.0], help="x y z spacing.")
    parser.add_argument("--case_id", action="append", default=None, help="Optional case_id filter; can repeat.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    ensure_dir(args.image_dir)
    ensure_dir(args.label_dir)
    df = pd.read_csv(args.source_csv)
    source_root = os.path.dirname(os.path.dirname(os.path.abspath(args.source_csv)))
    if args.case_id:
        keep = set(args.case_id)
        df = df[df["case_id"].isin(keep)].copy()
    rows = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Resampling ROI to 1mm"):
        case_id = row["case_id"]
        image_path = resolve_source_path(row.get("roi_image_path") or row["image_path"], source_root)
        label_path = resolve_source_path(row.get("roi_label_path") or row["label_path"], source_root)
        out_img = os.path.join(args.image_dir, f"{case_id}_roi_1mm_img.nii.gz")
        out_lab = os.path.join(args.label_dir, f"{case_id}_roi_1mm_lab.nii.gz")
        if args.overwrite or not (os.path.exists(out_img) and os.path.exists(out_lab)):
            img = sitk.ReadImage(image_path)
            lab = sitk.ReadImage(label_path)
            img_1mm = resample_to_spacing(img, spacing=tuple(args.spacing), is_label=False)
            lab_1mm = resample_to_spacing(lab, spacing=tuple(args.spacing), is_label=True)
            sitk.WriteImage(img_1mm, out_img)
            sitk.WriteImage(lab_1mm, out_lab)
        rows.append(
            {
                "case_id": case_id,
                "source_image_path": image_path,
                "source_label_path": label_path,
                "roi_1mm_image_path": out_img,
                "roi_1mm_label_path": out_lab,
                "spacing_x": float(args.spacing[0]),
                "spacing_y": float(args.spacing[1]),
                "spacing_z": float(args.spacing[2]),
            }
        )
    ensure_dir(os.path.dirname(args.output_csv))
    pd.DataFrame(rows).to_csv(args.output_csv, index=False)
    print(f"Saved: {args.output_csv}")


if __name__ == "__main__":
    main()
