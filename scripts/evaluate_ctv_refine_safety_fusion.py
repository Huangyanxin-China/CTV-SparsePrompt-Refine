#!/usr/bin/env python3
"""Evaluate conservative post-hoc fusion rules for CTV refine outputs.

The rules use only inference-available masks: pseudo label, refine prediction,
prompt/envelope channels saved in the cache. Validation metrics can be used to
select a fixed rule; test metrics are reported only after that fixed selection.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage, stats


def dice_score(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(bool)
    b = b.astype(bool)
    denom = int(a.sum() + b.sum())
    if denom == 0:
        return 1.0
    return float(2 * np.logical_and(a, b).sum() / denom)


def read_metric_cases(path: Path) -> list[str]:
    with path.open() as f:
        return [row["case"] for row in csv.DictReader(f)]


def load_split(result_dir: Path, split_name: str) -> list[dict]:
    if split_name == "val":
        cache_split = "Tr"
        metrics_path = result_dir / "val_metrics.csv"
        pred_dir = result_dir / "predictions_val"
    elif split_name == "test":
        cache_split = "Ts"
        metrics_path = result_dir / "test_metrics.csv"
        pred_dir = result_dir / "predictions_test"
    else:
        raise ValueError(f"Unknown split: {split_name}")

    rows = []
    for case_id in read_metric_cases(metrics_path):
        cache_path = result_dir / "cache" / cache_split / f"{case_id}.npz"
        pred_path = pred_dir / f"{case_id}.nii.gz"
        with np.load(cache_path) as data:
            y = data["y"].astype(bool)
            x = data["x"].astype(np.float32, copy=False)
            pseudo = x[1] > 0.5
            envelope = x[3] > 0.5
            prompt = x[4] > 0.5
            start = data["crop_start"].astype(int)
            stop = data["crop_stop"].astype(int)

        full_pred = sitk.GetArrayFromImage(sitk.ReadImage(str(pred_path))).astype(bool)
        crop = tuple(slice(int(a), int(b)) for a, b in zip(start, stop))
        refine = full_pred[crop]
        refine = (refine & envelope) | prompt

        union = pseudo | refine | prompt
        intersect = (pseudo & refine) | prompt
        adjacent = ndimage.binary_dilation(pseudo, iterations=2) & envelope
        add_adjacent = pseudo | (refine & adjacent) | prompt

        rows.append(
            {
                "case": case_id,
                "pseudo": dice_score(pseudo, y),
                "refine": dice_score(refine, y),
                "union": dice_score(union, y),
                "intersect": dice_score(intersect, y),
                "add_adjacent": dice_score(add_adjacent, y),
                "pseudo_voxels": int(pseudo.sum()),
                "refine_voxels": int(refine.sum()),
                "union_voxels": int(union.sum()),
                "gt_voxels": int(y.sum()),
                "vol_ratio_refine_to_pseudo": float(refine.sum() / max(1, int(pseudo.sum()))),
                "added_voxels": int(np.logical_and(refine, ~pseudo).sum()),
                "deleted_voxels": int(np.logical_and(pseudo, ~refine).sum()),
            }
        )
    return rows


def summarize(rows: list[dict], method: str) -> dict:
    pseudo = np.asarray([r["pseudo"] for r in rows], dtype=float)
    values = np.asarray([r[method] for r in rows], dtype=float)
    delta = values - pseudo
    summary = {
        "method": method,
        "n": int(len(rows)),
        "pseudo_mean": float(pseudo.mean()),
        "method_mean": float(values.mean()),
        "delta_mean": float(delta.mean()),
        "improved": int(np.sum(delta > 1e-8)),
        "worse": int(np.sum(delta < -1e-8)),
        "min_delta": float(delta.min()),
        "max_delta": float(delta.max()),
    }
    if len(rows) > 1:
        summary["paired_t_p_greater"] = float(stats.ttest_rel(values, pseudo, alternative="greater").pvalue)
        if np.any(np.abs(delta) > 1e-12):
            summary["wilcoxon_p_greater"] = float(
                stats.wilcoxon(values, pseudo, alternative="greater", zero_method="wilcox").pvalue
            )
        else:
            summary["wilcoxon_p_greater"] = None
    return summary


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result_dir",
        type=Path,
        default=Path("results/ctv_pseudo_refine_net_k7_oarroi_fastmargin_supervised_gpu1"),
    )
    parser.add_argument(
        "--out_dir",
        type=Path,
        default=Path("results/ctv_pseudo_refine_net_k7_oarroi_fastmargin_supervised_gpu1_safety_fusion_eval"),
    )
    args = parser.parse_args()

    methods = ["refine", "union", "intersect", "add_adjacent"]
    val_rows = load_split(args.result_dir, "val")
    test_rows = load_split(args.result_dir, "test")
    val_summary = [summarize(val_rows, method) for method in methods]
    test_summary = [summarize(test_rows, method) for method in methods]
    selected = max(val_summary, key=lambda row: row["method_mean"])["method"]
    summary = {
        "val": val_summary,
        "test": test_summary,
        "selected_by_val": selected,
        "selected_test": summarize(test_rows, selected),
        "note": (
            "All candidate rules use only pseudo/refine/prompt/envelope at inference. "
            "Method selection is based on validation mean Dice, not test labels."
        ),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_rows(args.out_dir / "val_safety_fusion_metrics.csv", val_rows)
    write_rows(args.out_dir / "test_safety_fusion_metrics.csv", test_rows)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
