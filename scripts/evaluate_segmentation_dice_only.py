#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
from collections import defaultdict

import numpy as np
import SimpleITK as sitk


def read_array(path):
    return sitk.GetArrayFromImage(sitk.ReadImage(path))


def dice_score(pred, gt):
    pred_sum = int(pred.sum())
    gt_sum = int(gt.sum())
    if pred_sum == 0 and gt_sum == 0:
        return 1.0
    denom = pred_sum + gt_sum
    if denom == 0:
        return float("nan")
    return float(2.0 * np.logical_and(pred, gt).sum() / denom)


def summarize(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return {"mean": None, "std": None, "n": 0}
    return {"mean": float(arr.mean()), "std": float(arr.std()), "n": int(arr.size)}


def main():
    parser = argparse.ArgumentParser(description="Fast Dice-only segmentation folder evaluation.")
    parser.add_argument("--gt_dir", required=True)
    parser.add_argument("--pred_dir", required=True)
    parser.add_argument("--classes", nargs="+", type=int, required=True)
    parser.add_argument("--class_names", nargs="*", default=None)
    parser.add_argument("--output_csv", required=True)
    parser.add_argument("--output_json", required=True)
    args = parser.parse_args()

    if args.class_names and len(args.class_names) != len(args.classes):
        raise ValueError("--class_names must have the same length as --classes")

    class_names = {
        cls: (args.class_names[i] if args.class_names else str(cls))
        for i, cls in enumerate(args.classes)
    }

    pred_files = sorted(
        f for f in os.listdir(args.pred_dir)
        if f.endswith(".nii.gz") or f.endswith(".nii")
    )
    rows = []
    skipped = []

    for pred_name in pred_files:
        pred_path = os.path.join(args.pred_dir, pred_name)
        gt_path = os.path.join(args.gt_dir, pred_name)
        if not os.path.exists(gt_path) and pred_name.endswith("_0000.nii.gz"):
            gt_path = os.path.join(args.gt_dir, pred_name.replace("_0000.nii.gz", ".nii.gz"))
        if not os.path.exists(gt_path):
            skipped.append({"case": pred_name, "reason": "missing_gt"})
            continue

        pred_arr = read_array(pred_path)
        gt_arr = read_array(gt_path)
        if pred_arr.shape != gt_arr.shape:
            skipped.append({
                "case": pred_name,
                "reason": f"shape_mismatch pred={pred_arr.shape} gt={gt_arr.shape}",
            })
            continue

        case = pred_name.replace(".nii.gz", "").replace(".nii", "")
        for cls in args.classes:
            pred_mask = pred_arr == cls
            gt_mask = gt_arr == cls
            gt_volume = int(gt_mask.sum())
            pred_volume = int(pred_mask.sum())
            vol_diff = pred_volume - gt_volume
            vol_diff_pct = float(vol_diff / gt_volume * 100.0) if gt_volume > 0 else float("nan")
            rows.append({
                "case": case,
                "class_id": cls,
                "class_name": class_names[cls],
                "dice": dice_score(pred_mask, gt_mask),
                "gt_voxels": gt_volume,
                "pred_voxels": pred_volume,
                "volume_diff_voxels": vol_diff,
                "volume_diff_percent": vol_diff_pct,
            })

    os.makedirs(os.path.dirname(args.output_csv), exist_ok=True)
    fieldnames = [
        "case", "class_id", "class_name", "dice",
        "gt_voxels", "pred_voxels", "volume_diff_voxels", "volume_diff_percent",
    ]
    with open(args.output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    per_class = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cls = str(row["class_id"])
        for key in ("dice", "volume_diff_percent"):
            value = row[key]
            if isinstance(value, float) and math.isnan(value):
                continue
            per_class[cls][key].append(value)

    summary = {
        "gt_dir": args.gt_dir,
        "pred_dir": args.pred_dir,
        "num_predictions": len(pred_files),
        "num_rows": len(rows),
        "skipped": skipped,
        "per_class": {
            cls: {
                metric: summarize(values)
                for metric, values in metrics.items()
            }
            for cls, metrics in sorted(per_class.items(), key=lambda x: int(x[0]))
        },
        "overall_foreground": {
            "dice": summarize([row["dice"] for row in rows]),
            "volume_diff_percent": summarize([row["volume_diff_percent"] for row in rows]),
        },
    }

    os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["per_class"], indent=2))
    print("Wrote", args.output_csv)
    print("Wrote", args.output_json)


if __name__ == "__main__":
    main()
