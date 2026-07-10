#!/usr/bin/env python3
"""Strict folder-level evaluation for aligned medical-image segmentations."""

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

try:
    from medpy.metric import binary as medpy_binary
except Exception:
    medpy_binary = None


NIFTI_SUFFIXES = (".nii.gz", ".nii")


def read_array(path: Path):
    image = sitk.ReadImage(str(path))
    return sitk.GetArrayFromImage(image), image


def case_id_from_name(name: str) -> str:
    for suffix in NIFTI_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if name.endswith("_0000"):
        name = name[:-5]
    return name


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


def surface_metrics(pred, gt, spacing_zyx):
    if not pred.any() and not gt.any():
        return 0.0, 0.0, "both_empty"
    if not pred.any() or not gt.any():
        return float("nan"), float("nan"), "one_empty"
    try:
        return (
            float(medpy_binary.hd95(pred, gt, voxelspacing=spacing_zyx)),
            float(medpy_binary.asd(pred, gt, voxelspacing=spacing_zyx)),
            "ok",
        )
    except Exception as exc:
        return float("nan"), float("nan"), f"error:{type(exc).__name__}"


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


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    ensure_dir(str(path.parent) if str(path.parent) != "." else "")
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a prediction folder against the complete ground-truth manifest. "
            "Missing predictions and geometry mismatches fail by default."
        )
    )
    parser.add_argument("--gt_dir", type=Path, required=True)
    parser.add_argument("--pred_dir", type=Path, required=True)
    parser.add_argument("--classes", nargs="+", type=int, required=True)
    parser.add_argument("--class_names", nargs="*", default=None)
    parser.add_argument("--output_csv", type=Path, required=True)
    parser.add_argument("--output_json", type=Path, required=True)
    parser.add_argument(
        "--allow_missing",
        action="store_true",
        help="Debug only: evaluate available cases while reporting every missing prediction.",
    )
    parser.add_argument(
        "--skip_invalid_geometry",
        action="store_true",
        help="Debug only: skip, rather than fail on, images that do not share the GT physical grid.",
    )
    parser.add_argument(
        "--skip_surface_metrics",
        action="store_true",
        help="Skip HD95/ASD. Otherwise MedPy is required.",
    )
    args = parser.parse_args()

    if args.class_names and len(args.class_names) != len(args.classes):
        parser.error("--class_names must have the same length as --classes")
    if not args.gt_dir.is_dir() or not args.pred_dir.is_dir():
        parser.error("--gt_dir and --pred_dir must be existing directories")
    if medpy_binary is None and not args.skip_surface_metrics:
        parser.error("MedPy is required for HD95/ASD; install medpy or pass --skip_surface_metrics")

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
            f"Missing predictions for {len(missing_predictions)} GT cases: {preview}. "
            "Pass --allow_missing only for an explicitly documented debug run."
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
        if pred_arr.shape != gt_arr.shape:
            raise ValueError(
                f"{case}: array shape mismatch pred={pred_arr.shape} gt={gt_arr.shape}"
            )

        spacing_zyx = tuple(float(v) for v in gt_img.GetSpacing()[::-1])
        for cls in args.classes:
            pred_mask = pred_arr == cls
            gt_mask = gt_arr == cls
            gt_volume = int(gt_mask.sum())
            pred_volume = int(pred_mask.sum())
            vol_diff = pred_volume - gt_volume
            vol_diff_pct = (
                float(vol_diff / gt_volume * 100.0) if gt_volume > 0 else float("nan")
            )
            if args.skip_surface_metrics:
                hd95, asd, surface_status = float("nan"), float("nan"), "skipped"
            else:
                hd95, asd, surface_status = surface_metrics(
                    pred_mask, gt_mask, spacing_zyx
                )
            rows.append(
                {
                    "case": case,
                    "class_id": cls,
                    "class_name": class_names[cls],
                    "dice": dice_score(pred_mask, gt_mask),
                    "hd95": hd95,
                    "asd": asd,
                    "surface_status": surface_status,
                    "gt_voxels": gt_volume,
                    "pred_voxels": pred_volume,
                    "volume_diff_voxels": vol_diff,
                    "volume_diff_percent": vol_diff_pct,
                }
            )

    fieldnames = [
        "case",
        "class_id",
        "class_name",
        "dice",
        "hd95",
        "asd",
        "surface_status",
        "gt_voxels",
        "pred_voxels",
        "volume_diff_voxels",
        "volume_diff_percent",
    ]
    write_csv(args.output_csv, rows, fieldnames)

    per_class = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cls = str(row["class_id"])
        for key in ("dice", "hd95", "asd", "volume_diff_percent"):
            per_class[cls][key].append(row[key])

    macro_class_case = {
        metric: summarize([row[metric] for row in rows])
        for metric in ("dice", "hd95", "asd", "volume_diff_percent")
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
        "surface_metrics_available": bool(
            medpy_binary is not None and not args.skip_surface_metrics
        ),
        "surface_status_counts": {
            status: sum(row["surface_status"] == status for row in rows)
            for status in sorted({row["surface_status"] for row in rows})
        },
        "per_class": {
            cls: {
                metric: summarize(values)
                for metric, values in metrics.items()
            }
            for cls, metrics in sorted(per_class.items(), key=lambda item: int(item[0]))
        },
        "macro_class_case": macro_class_case,
        "notes": [
            "macro_class_case averages per-class, per-case rows; it is not a merged foreground mask.",
            "Undefined surface distances remain visible through n_undefined and surface_status_counts.",
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
