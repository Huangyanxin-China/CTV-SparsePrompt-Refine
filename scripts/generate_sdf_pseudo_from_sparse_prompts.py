#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import os.path as osp
from collections import defaultdict
from glob import glob

import numpy as np
import SimpleITK as sitk
from scipy import ndimage


def read_image(path):
    image = sitk.ReadImage(path)
    return sitk.GetArrayFromImage(image), image


def write_like(arr, ref_image, path, dtype=None):
    if dtype is not None:
        arr = arr.astype(dtype)
    out = sitk.GetImageFromArray(arr)
    out.CopyInformation(ref_image)
    sitk.WriteImage(out, path)


def signed_distance_2d(mask2d, spacing_yx=(1.0, 1.0)):
    mask2d = mask2d.astype(bool)
    if not mask2d.any():
        return np.full(mask2d.shape, -1e6, dtype=np.float32)
    inside = ndimage.distance_transform_edt(mask2d, sampling=spacing_yx)
    outside = ndimage.distance_transform_edt(~mask2d, sampling=spacing_yx)
    return (inside - outside).astype(np.float32)


def sdf_from_sparse_prompt(prompt, spacing_xyz, shrink_per_mm=1.0, max_end_distance_mm=-1.0):
    prompt = prompt.astype(bool)
    z_indices = np.where(prompt.reshape(prompt.shape[0], -1).any(axis=1))[0]
    if z_indices.size == 0:
        return np.full(prompt.shape, -1e6, dtype=np.float32), z_indices

    spacing_x, spacing_y, spacing_z = [float(v) for v in spacing_xyz]
    spacing_yx = (spacing_y, spacing_x)
    sdfs = {int(z): signed_distance_2d(prompt[int(z)], spacing_yx=spacing_yx) for z in z_indices}
    out = np.full(prompt.shape, -1e6, dtype=np.float32)

    for z in range(prompt.shape[0]):
        if z in sdfs:
            sdf = sdfs[int(z)]
        elif z < z_indices[0]:
            dz_mm = float(z_indices[0] - z) * spacing_z
            if max_end_distance_mm >= 0 and dz_mm > float(max_end_distance_mm):
                continue
            sdf = sdfs[int(z_indices[0])] - float(shrink_per_mm) * dz_mm
        elif z > z_indices[-1]:
            dz_mm = float(z - z_indices[-1]) * spacing_z
            if max_end_distance_mm >= 0 and dz_mm > float(max_end_distance_mm):
                continue
            sdf = sdfs[int(z_indices[-1])] - float(shrink_per_mm) * dz_mm
        else:
            right = int(np.searchsorted(z_indices, z))
            z0 = int(z_indices[right - 1])
            z1 = int(z_indices[right])
            t = (z - z0) / max(float(z1 - z0), 1.0)
            sdf = (1.0 - t) * sdfs[z0] + t * sdfs[z1]
        out[z] = sdf.astype(np.float32)
    return out, z_indices


def dice_score(pred, gt):
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    denom = int(pred.sum()) + int(gt.sum())
    if denom == 0:
        return 1.0
    return float(2.0 * np.logical_and(pred, gt).sum() / denom)


def surface_metrics(pred, gt, spacing_xyz):
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    if not pred.any() and not gt.any():
        return 0.0, 0.0
    if not pred.any() or not gt.any():
        return float("nan"), float("nan")

    # Crop to the union bbox for speed and to avoid allocating distance maps on
    # irrelevant background.
    pts = np.argwhere(pred | gt)
    pad_mm = 20.0
    spacing_zyx = np.asarray(spacing_xyz[::-1], dtype=float)
    pad = np.ceil(pad_mm / np.maximum(spacing_zyx, 1e-6)).astype(int)
    lo = np.maximum(pts.min(axis=0) - pad, 0)
    hi = np.minimum(pts.max(axis=0) + pad + 1, np.asarray(pred.shape))
    slc = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))
    pred = pred[slc]
    gt = gt[slc]

    structure = ndimage.generate_binary_structure(3, 1)
    pred_surface = pred ^ ndimage.binary_erosion(pred, structure=structure, border_value=0)
    gt_surface = gt ^ ndimage.binary_erosion(gt, structure=structure, border_value=0)
    if not pred_surface.any() or not gt_surface.any():
        return float("nan"), float("nan")
    dt_pred = ndimage.distance_transform_edt(~pred_surface, sampling=spacing_zyx)
    dt_gt = ndimage.distance_transform_edt(~gt_surface, sampling=spacing_zyx)
    distances = np.concatenate([dt_gt[pred_surface], dt_pred[gt_surface]])
    if distances.size == 0:
        return float("nan"), float("nan")
    return float(np.percentile(distances, 95)), float(distances.mean())


def summarize(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return {"mean": None, "std": None, "n": 0}
    return {"mean": float(arr.mean()), "std": float(arr.std()), "n": int(arr.size)}


def case_names_from_prompt_dir(prompt_dir):
    return [osp.basename(p).replace(".nii.gz", "") for p in sorted(glob(osp.join(prompt_dir, "*.nii.gz")))]


def main():
    parser = argparse.ArgumentParser(description="Generate SDF pseudo labels from sparse prompt masks and evaluate them.")
    parser.add_argument("--prompt_dir", required=True)
    parser.add_argument("--gt_dir", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--target_label", type=int, default=1)
    parser.add_argument("--shrink_per_mm", type=float, default=1.0)
    parser.add_argument("--max_end_distance_mm", type=float, default=-1.0)
    parser.add_argument("--output_csv", required=True)
    parser.add_argument("--output_json", required=True)
    parser.add_argument("--write_sdf", action="store_true")
    args = parser.parse_args()

    label_dir = osp.join(args.out_dir, "labels")
    sdf_dir = osp.join(args.out_dir, "sdf")
    os.makedirs(label_dir, exist_ok=True)
    if args.write_sdf:
        os.makedirs(sdf_dir, exist_ok=True)
    os.makedirs(osp.dirname(args.output_csv), exist_ok=True)
    os.makedirs(osp.dirname(args.output_json), exist_ok=True)

    rows = []
    skipped = []
    for case in case_names_from_prompt_dir(args.prompt_dir):
        prompt_path = osp.join(args.prompt_dir, f"{case}.nii.gz")
        gt_path = osp.join(args.gt_dir, f"{case}.nii.gz")
        if not osp.exists(gt_path):
            skipped.append({"case": case, "reason": "missing_gt"})
            continue

        prompt_arr, prompt_img = read_image(prompt_path)
        gt_arr, gt_img = read_image(gt_path)
        if prompt_arr.shape != gt_arr.shape:
            skipped.append({"case": case, "reason": f"shape_mismatch prompt={prompt_arr.shape} gt={gt_arr.shape}"})
            continue

        prompt = prompt_arr == int(args.target_label)
        gt = gt_arr == int(args.target_label)
        sdf, annotated_z = sdf_from_sparse_prompt(
            prompt,
            spacing_xyz=gt_img.GetSpacing(),
            shrink_per_mm=args.shrink_per_mm,
            max_end_distance_mm=args.max_end_distance_mm,
        )
        pred = sdf >= 0
        pred[annotated_z] = prompt[annotated_z]

        pred_path = osp.join(label_dir, f"{case}.nii.gz")
        write_like(pred.astype(np.uint8), gt_img, pred_path, dtype=np.uint8)
        if args.write_sdf:
            write_like(sdf.astype(np.float32), gt_img, osp.join(sdf_dir, f"{case}.nii.gz"), dtype=np.float32)

        prompt_slice_mask = np.zeros(gt.shape[0], dtype=bool)
        prompt_slice_mask[annotated_z] = True
        unseen_slice_mask = ~prompt_slice_mask

        gt_volume = int(gt.sum())
        pred_volume = int(pred.sum())
        hd95, asd = surface_metrics(pred, gt, spacing_xyz=gt_img.GetSpacing())
        rows.append(
            {
                "case": case,
                "class_id": int(args.target_label),
                "class_name": "ctv",
                "n_prompt_slices": int(len(annotated_z)),
                "annotated_z": ";".join(str(int(z)) for z in annotated_z),
                "dice": dice_score(pred, gt),
                "dice_prompt_slices": dice_score(pred[prompt_slice_mask], gt[prompt_slice_mask]) if prompt_slice_mask.any() else float("nan"),
                "dice_unseen_slices": dice_score(pred[unseen_slice_mask], gt[unseen_slice_mask]) if unseen_slice_mask.any() else float("nan"),
                "hd95": hd95,
                "asd": asd,
                "gt_voxels": gt_volume,
                "pred_voxels": pred_volume,
                "prompt_voxels": int(prompt.sum()),
                "volume_diff_voxels": pred_volume - gt_volume,
                "volume_diff_percent": float((pred_volume - gt_volume) / gt_volume * 100.0) if gt_volume > 0 else float("nan"),
                "pseudo_label_path": pred_path,
                "prompt_path": prompt_path,
            }
        )

    fieldnames = [
        "case",
        "class_id",
        "class_name",
        "n_prompt_slices",
        "annotated_z",
        "dice",
        "dice_prompt_slices",
        "dice_unseen_slices",
        "hd95",
        "asd",
        "gt_voxels",
        "pred_voxels",
        "prompt_voxels",
        "volume_diff_voxels",
        "volume_diff_percent",
        "pseudo_label_path",
        "prompt_path",
    ]
    with open(args.output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    metrics = defaultdict(list)
    for row in rows:
        for key in ("dice", "dice_prompt_slices", "dice_unseen_slices", "hd95", "asd", "volume_diff_percent"):
            value = row[key]
            if isinstance(value, float) and math.isnan(value):
                continue
            metrics[key].append(value)
    summary = {
        "prompt_dir": args.prompt_dir,
        "gt_dir": args.gt_dir,
        "pred_dir": label_dir,
        "num_predictions": len(rows),
        "skipped": skipped,
        "metrics": {key: summarize(values) for key, values in metrics.items()},
    }
    with open(args.output_json, "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["metrics"], indent=2))
    print("Wrote", args.output_csv)
    print("Wrote", args.output_json)
    print("Predictions:", label_dir)


if __name__ == "__main__":
    main()
