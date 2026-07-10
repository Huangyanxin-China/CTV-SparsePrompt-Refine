#!/usr/bin/env python3
"""Fast, strict Dice-only folder evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.io import assert_same_geometry, ensure_dir


NIFTI_SUFFIXES = (".nii.gz", ".nii")


def read_array(path: Path):
    image = sitk.ReadImage(str(path))
    return sitk.GetArrayFromImage(image), image


def case_id_from_name(name: str) -> str:
    for suffix in NIFTI_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name[:-5] if name.endswith("_0000") else name


def index_nifti_files(directory: Path) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file() or not path.name.endswith(NIFTI_SUFFIXES):
            continue
        case_id = case_id_from_name(path.name)
        if case_id in indexed:
            raise ValueError(
                f"Duplicate files resolve to case {case_id!r}: {indexed[case_id]} and {path}"
            )
        indexed[case_id] = path
    return indexed


def dice_score(pred, gt):
    pred_sum = int(pred.sum())
    gt_sum = int(gt.sum())
    if pred_sum == 0 and gt_sum == 0:
        return 1.0
    return float(2.0 * np.logical_and(pred, gt).sum() / (pred_sum + gt_sum))


def summarize(values):
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {
            "mean": None,
            "std": None,
            "n": 0,
            "n_total": int(arr.size),
            "n_undefined": int(arr.size),
        }
    return {
        "mean": float(finite.mean()),
        "std": float(finite.std()),
        "n": int(finite.size),
        "n_total": int(arr.size),
        "n_undefined": int(arr.size - finite.size),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Dice against the complete GT manifest; missing predictions fail by default."
    )
    parser.add_argument("--gt_dir", type=Path, required=True)
    parser.add_argument("--pred_dir", type=Path, required=True)
    parser.add_argument("--classes", nargs="+", type=int, required=True)
    parser.add_argument("--class_names", nargs="*", default=None)
    parser.add_argument("--output_csv", type=Path, required=True)
    parser.add_argument("--output_json", type=Path, required=True)
    parser.add_argument("--allow_missing", action="store_true", help="Debug only.")
    parser.add_argument("--skip_invalid_geometry", action="store_true", help="Debug only.")
    args = parser.parse_args()

    if args.class_names and len(args.class_names) != len(args.classes):
        parser.error("--class_names must have the same length as --classes")
    if not args.gt_dir.is_dir() or not args.pred_dir.is_dir():
        parser.error("--gt_dir and --pred_dir must be existing directories")

    class_names = {
        cls: (args.class_names[i] if args.class_names else str(cls))
        for i, cls in enumerate(args.classes)
    }
    gt_files = index_nifti_files(args.gt_dir)
    pred_files = index_nifti_files(args.pred_dir)
    missing_predictions = sorted(set(gt_files) - set(pred_files))
    unexpected_predictions = sorted(set(pred_files) - set(gt_files))
    if missing_predictions and not args.allow_missing:
        preview = ", ".join(missing_predictions[:10])
        raise FileNotFoundError(
            f"Missing predictions for {len(missing_predictions)} GT cases: {preview}"
        )

    rows = []
    skipped = [
        {"case": case, "reason": "missing_prediction"} for case in missing_predictions
    ]
    skipped.extend(
        {"case": case, "reason": "prediction_without_ground_truth"}
        for case in unexpected_predictions
    )

    for case in sorted(set(gt_files) & set(pred_files)):
        pred_arr, pred_img = read_array(pred_files[case])
        gt_arr, gt_img = read_array(gt_files[case])
        try:
            assert_same_geometry(gt_img, pred_img, "ground truth", "prediction")
        except ValueError as exc:
            if not args.skip_invalid_geometry:
                raise
            skipped.append({"case": case, "reason": str(exc)})
            continue
        for cls in args.classes:
            pred_mask = pred_arr == cls
            gt_mask = gt_arr == cls
            gt_volume = int(gt_mask.sum())
            pred_volume = int(pred_mask.sum())
            vol_diff = pred_volume - gt_volume
            rows.append(
                {
                    "case": case,
                    "class_id": cls,
                    "class_name": class_names[cls],
                    "dice": dice_score(pred_mask, gt_mask),
                    "gt_voxels": gt_volume,
                    "pred_voxels": pred_volume,
                    "volume_diff_voxels": vol_diff,
                    "volume_diff_percent": (
                        float(vol_diff / gt_volume * 100.0)
                        if gt_volume > 0
                        else float("nan")
                    ),
                }
            )

    ensure_dir(str(args.output_csv.parent) if str(args.output_csv.parent) != "." else "")
    with args.output_csv.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case",
                "class_id",
                "class_name",
                "dice",
                "gt_voxels",
                "pred_voxels",
                "volume_diff_voxels",
                "volume_diff_percent",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    per_class = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cls = str(row["class_id"])
        for key in ("dice", "volume_diff_percent"):
            per_class[cls][key].append(row[key])

    macro_class_case = {
        "dice": summarize([row["dice"] for row in rows]),
        "volume_diff_percent": summarize(
            [row["volume_diff_percent"] for row in rows]
        ),
    }
    summary = {
        "gt_dir": str(args.gt_dir),
        "pred_dir": str(args.pred_dir),
        "num_ground_truth": len(gt_files),
        "num_predictions": len(pred_files),
        "num_evaluated_cases": len({row["case"] for row in rows}),
        "num_rows": len(rows),
        "missing_predictions": missing_predictions,
        "unexpected_predictions": unexpected_predictions,
        "skipped": skipped,
        "per_class": {
            cls: {
                metric: summarize(values)
                for metric, values in metrics.items()
            }
            for cls, metrics in sorted(per_class.items(), key=lambda item: int(item[0]))
        },
        "macro_class_case": macro_class_case,
        "notes": [
            "macro_class_case averages per-class, per-case rows; it is not a merged foreground mask."
        ],
    }

    ensure_dir(str(args.output_json.parent) if str(args.output_json.parent) != "." else "")
    with args.output_json.open("w") as f:
        json.dump(summary, f, indent=2, allow_nan=True)

    print(json.dumps(summary["per_class"], indent=2, allow_nan=True))
    print("Wrote", args.output_csv)
    print("Wrote", args.output_json)


if __name__ == "__main__":
    main()
