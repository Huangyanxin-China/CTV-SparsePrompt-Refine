#!/usr/bin/env python3
"""Evaluate a non-SDF sparse-slice interpolation baseline.

The baseline uses the same full-slice CTV prompts as the main K=7 sparse-prompt
setting, but it only linearly interpolates binary mask occupancy along z. It does
not use CT intensities, OAR anatomy, signed distance fields, or learned models.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import os.path as osp
import sys
from glob import glob
from pathlib import Path

import numpy as np
import SimpleITK as sitk


ROOT = str(Path(__file__).resolve().parents[1])
SCRIPT_DIR = osp.join(ROOT, "scripts")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import run_sparse_prompt_core_envelope_workflow as wf


def read_image(path: str):
    image = sitk.ReadImage(path)
    return sitk.GetArrayFromImage(image), image


def write_like(arr: np.ndarray, ref: sitk.Image, path: str) -> None:
    out = sitk.GetImageFromArray(arr.astype(np.uint8))
    out.CopyInformation(ref)
    sitk.WriteImage(out, path)


def case_names(label_dir: str) -> list[str]:
    return [osp.basename(path).replace(".nii.gz", "") for path in sorted(glob(osp.join(label_dir, "*.nii.gz")))]


def linear_mask_interpolation(prompt: np.ndarray) -> np.ndarray:
    """Interpolate binary prompt masks voxelwise between prompted z-slices."""
    prompt = prompt.astype(bool)
    out = np.zeros_like(prompt, dtype=bool)
    z_indices = np.where(prompt.reshape(prompt.shape[0], -1).any(axis=1))[0]
    if z_indices.size == 0:
        return out

    out[z_indices] = prompt[z_indices]
    if z_indices.size == 1:
        return out

    prompt_float = prompt.astype(np.float32)
    for left, right in zip(z_indices[:-1], z_indices[1:]):
        left = int(left)
        right = int(right)
        if right <= left + 1:
            continue
        for z in range(left + 1, right):
            t = float(z - left) / float(right - left)
            occupancy = (1.0 - t) * prompt_float[left] + t * prompt_float[right]
            out[z] = occupancy >= 0.5
    return out


def summarize(values: list[float]) -> dict[str, float | int | None]:
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return {"mean": None, "std": None, "n": 0}
    return {"mean": float(arr.mean()), "std": float(arr.std()), "n": int(arr.size)}


def metric_row(case_id: str, pred: np.ndarray, gt: np.ndarray, prompt: np.ndarray, spacing_xyz) -> dict[str, object]:
    prompt_z = np.where(prompt.reshape(prompt.shape[0], -1).any(axis=1))[0]
    prompt_z_mask = np.zeros(gt.shape[0], dtype=bool)
    prompt_z_mask[prompt_z] = True
    hd95, asd = wf.surface_metrics(pred, gt, spacing_xyz)
    ppv, rec = wf.precision_recall(pred, gt)
    gt_voxels = int(gt.sum())
    pred_voxels = int(pred.sum())
    return {
        "case": case_id,
        "method": "linear_mask_interpolation_k7",
        "n_prompt_slices": int(prompt_z.size),
        "selected_z": ";".join(str(int(z)) for z in prompt_z),
        "dice": wf.dice_score(pred, gt),
        "dice_prompt_slices": wf.dice_score(pred[prompt_z_mask], gt[prompt_z_mask]) if prompt_z_mask.any() else float("nan"),
        "dice_unseen_slices": wf.dice_score(pred[~prompt_z_mask], gt[~prompt_z_mask]) if (~prompt_z_mask).any() else float("nan"),
        "precision": ppv,
        "recall": rec,
        "hd95": hd95,
        "asd": asd,
        "gt_voxels": gt_voxels,
        "pred_voxels": pred_voxels,
        "volume_diff_voxels": pred_voxels - gt_voxels,
        "volume_diff_percent": float((pred_voxels - gt_voxels) / gt_voxels * 100.0) if gt_voxels > 0 else float("nan"),
    }


def write_csv(path: str, rows: list[dict[str, object]]) -> None:
    os.makedirs(osp.dirname(path), exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a traditional sparse-slice mask interpolation baseline.")
    parser.add_argument("--gt_dir", default=osp.join(ROOT, "nnunet_runs/raw/Dataset015_CTV_Dataset004Split/labelsTs"))
    parser.add_argument(
        "--prompt_dir",
        default=osp.join(ROOT, "external_runs/sammed3d_sparse_prompt/ctv_k7_even_nonempty_click7/_sparse_prompts"),
    )
    parser.add_argument("--out_dir", default=osp.join(ROOT, "results/traditional_linear_mask_interpolation_k7"))
    parser.add_argument("--write_predictions", action="store_true")
    args = parser.parse_args()

    out_label_dir = osp.join(args.out_dir, "labels")
    if args.write_predictions:
        os.makedirs(out_label_dir, exist_ok=True)

    rows: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    for case_id in case_names(args.gt_dir):
        gt_path = osp.join(args.gt_dir, f"{case_id}.nii.gz")
        prompt_path = osp.join(args.prompt_dir, f"{case_id}.nii.gz")
        if not osp.exists(prompt_path):
            skipped.append({"case": case_id, "reason": "missing prompt"})
            continue
        gt_arr, gt_img = read_image(gt_path)
        prompt_arr, _ = read_image(prompt_path)
        gt = gt_arr > 0
        prompt = prompt_arr > 0
        if gt.shape != prompt.shape:
            skipped.append({"case": case_id, "reason": f"shape mismatch gt={gt.shape} prompt={prompt.shape}"})
            continue
        pred = linear_mask_interpolation(prompt)
        pred[prompt] = True
        rows.append(metric_row(case_id, pred, gt, prompt, gt_img.GetSpacing()))
        if args.write_predictions:
            write_like(pred, gt_img, osp.join(out_label_dir, f"{case_id}.nii.gz"))

    write_csv(osp.join(args.out_dir, "per_case_metrics.csv"), rows)
    metric_names = [
        "dice",
        "dice_prompt_slices",
        "dice_unseen_slices",
        "precision",
        "recall",
        "hd95",
        "asd",
        "volume_diff_percent",
    ]
    summary = {name: summarize([float(row[name]) for row in rows]) for name in metric_names}
    payload = {
        "method": "linear_mask_interpolation_k7",
        "prompt_dir": args.prompt_dir,
        "gt_dir": args.gt_dir,
        "num_predictions": len(rows),
        "skipped": skipped,
        "metrics": summary,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    with open(osp.join(args.out_dir, "summary.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
