#!/usr/bin/env python3
"""Compute surface metrics for the selected K=7 preprocessing variant."""

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
from scipy.stats import wilcoxon


ROOT = str(Path(__file__).resolve().parents[1])
SCRIPT_DIR = osp.join(ROOT, "scripts")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import run_sparse_prompt_core_envelope_workflow as wf
import run_k7_preprocess_variant_screen as screen
from run_traditional_linear_mask_interpolation_baseline import linear_mask_interpolation


def case_names(label_dir: str) -> list[str]:
    return [osp.basename(p).replace(".nii.gz", "") for p in sorted(glob(osp.join(label_dir, "*.nii.gz")))]


def read_label(path: str):
    image = sitk.ReadImage(path)
    return sitk.GetArrayFromImage(image) > 0, image


def summarize(values: list[float]) -> str:
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return "--"
    return f"{arr.mean():.3f} +/- {arr.std():.3f}"


def summarize_percent(values: list[float]) -> str:
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return "--"
    return f"{arr.mean():.1f} +/- {arr.std():.1f}"


def mean_std(values: list[float]) -> dict:
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return {"mean": None, "std": None, "n": 0}
    return {"mean": float(arr.mean()), "std": float(arr.std()), "n": int(arr.size)}


def prompt_z_mask(prompt: np.ndarray) -> np.ndarray:
    z = np.where(prompt.reshape(prompt.shape[0], -1).any(axis=1))[0]
    mask = np.zeros(prompt.shape[0], dtype=bool)
    mask[z] = True
    return mask


def build_candidates(gt: np.ndarray, gt_img, case_id: str, k: int, strategy: str, profile: str):
    selected_z = wf.select_sparse_slices(gt, int(k), strategy, case_id)
    prompt = wf.make_prompt(gt, selected_z)
    linear = linear_mask_interpolation(prompt).astype(bool)
    linear[prompt] = True

    oar = np.zeros_like(gt, dtype=np.uint8)
    methods, support, n_candidates = wf.build_methods(prompt, selected_z, gt_img.GetSpacing(), oar, profile)
    base = methods["sdf_base"].astype(bool)
    core = methods["core_only"].astype(bool)
    support_100 = screen.support_mask(support, 1.0, prompt)
    inter = (linear & core)
    inter[prompt] = True

    selected_z = np.asarray(selected_z, dtype=int)
    shape = screen.prompt_shape_features(gt, selected_z)
    features = {
        "split": "test",
        "subject": screen.subject_id(case_id),
        "case": case_id,
        "selected_z": ";".join(str(int(z)) for z in selected_z),
        "n_selected": int(selected_z.size),
        "z_extent": int(selected_z[-1] - selected_z[0]) if selected_z.size else 0,
        "z_gap_mean": float(np.diff(selected_z).mean()) if selected_z.size > 1 else 0.0,
        "n_candidates": int(n_candidates),
        "core_linear_agreement": wf.dice_score(core, linear),
        "base_linear_agreement": wf.dice_score(base, linear),
        "core_linear_vol_ratio": float(core.sum() / max(int(linear.sum()), 1)),
        "base_linear_vol_ratio": float(base.sum() / max(int(linear.sum()), 1)),
        "core_base_vol_ratio": float(core.sum() / max(int(base.sum()), 1)),
        **shape,
    }
    preds = {
        "linear": linear,
        "sdf_core": core,
        "support_100": support_100,
        "linear_core_intersection": inter,
    }
    return selected_z, prompt, features, preds


def apply_threshold_rule(features: dict, rule: dict) -> str:
    cond = (
        float(features[rule["feature"]]) < float(rule["threshold"])
        if rule["op"] == "lt"
        else float(features[rule["feature"]]) >= float(rule["threshold"])
    )
    return rule["method_if_true"] if cond else rule["method_if_false"]


def metric_row(case_id: str, method: str, pred: np.ndarray, gt: np.ndarray, prompt: np.ndarray, spacing_xyz) -> dict:
    pzm = prompt_z_mask(prompt)
    hd95, asd = wf.surface_metrics(pred, gt, spacing_xyz)
    ppv, rec = wf.precision_recall(pred, gt)
    gt_voxels = int(gt.sum())
    pred_voxels = int(pred.sum())
    return {
        "case": case_id,
        "subject": screen.subject_id(case_id),
        "method": method,
        "dice": wf.dice_score(pred, gt),
        "dice_unseen_slices": wf.dice_score(pred[~pzm], gt[~pzm]) if (~pzm).any() else float("nan"),
        "precision": ppv,
        "recall": rec,
        "hd95": hd95,
        "asd": asd,
        "gt_voxels": gt_voxels,
        "pred_voxels": pred_voxels,
        "volume_diff_percent": float((pred_voxels - gt_voxels) / gt_voxels * 100.0) if gt_voxels > 0 else float("nan"),
    }


def paired(rows: list[dict], a: str, b: str, subject_level: bool = False) -> dict:
    key = "subject" if subject_level else "case"
    by_key: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        by_key.setdefault(row[key], {}).setdefault(row["method"], []).append(float(row["dice"]))
    delta = []
    for vals in by_key.values():
        if a in vals and b in vals:
            delta.append(float(np.mean(vals[a]) - np.mean(vals[b])))
    arr = np.asarray(delta, dtype=float)
    if arr.size == 0:
        return {"n": 0}
    try:
        p = float(wilcoxon(arr).pvalue) if np.any(np.abs(arr) > 1e-12) else 1.0
    except ValueError:
        p = 1.0
    return {
        "n": int(arr.size),
        "mean_delta": float(arr.mean()),
        "improved": int((arr > 0).sum()),
        "worse": int((arr < 0).sum()),
        "p": p,
    }


def write_csv(path: str, rows: list[dict]) -> None:
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
    parser = argparse.ArgumentParser(description="Summarize K=7 sparse-prompt variant surface metrics for local labels.")
    parser.add_argument("--label_dir", required=True, help="Local target-label directory.")
    parser.add_argument("--variant_summary", default=osp.join(ROOT, "results/data_preprocess_variant_screen_k7_20260602/summary.json"))
    parser.add_argument("--out_dir", default=osp.join(ROOT, "results/data_preprocess_variant_screen_k7_20260602"))
    parser.add_argument("--k", type=int, default=7)
    parser.add_argument("--strategy", default="even_nonempty")
    parser.add_argument("--profile", default="current")
    args = parser.parse_args()

    summary = json.load(open(args.variant_summary))
    threshold_rule = summary["threshold_rule"]
    rows: list[dict] = []
    features: list[dict] = []
    for idx, case_id in enumerate(case_names(args.label_dir), start=1):
        gt, gt_img = read_label(osp.join(args.label_dir, f"{case_id}.nii.gz"))
        if not gt.any():
            continue
        _, prompt, feat, preds = build_candidates(gt, gt_img, case_id, args.k, args.strategy, args.profile)
        chosen = apply_threshold_rule(feat, threshold_rule)
        preds["train_calibrated_support_intersection_rule"] = preds[chosen]
        feat["threshold_rule_chosen_source"] = chosen
        features.append(feat)
        for method, pred in preds.items():
            rows.append(metric_row(case_id, method, pred, gt, prompt, gt_img.GetSpacing()))
        print(f"test {idx:03d} {case_id} chosen={chosen}", flush=True)

    write_csv(osp.join(args.out_dir, "test_metrics_with_surface.csv"), rows)
    write_csv(osp.join(args.out_dir, "test_features_with_rule_choice.csv"), features)

    methods = ["linear", "sdf_core", "support_100", "linear_core_intersection", "train_calibrated_support_intersection_rule"]
    table = []
    full = {"methods": {}, "paired_scan": {}, "paired_subject": {}, "threshold_rule": threshold_rule}
    for method in methods:
        sub = [r for r in rows if r["method"] == method]
        table.append(
            {
                "method": method,
                "n": len(sub),
                "dice": summarize([float(r["dice"]) for r in sub]),
                "unseen_dice": summarize([float(r["dice_unseen_slices"]) for r in sub]),
                "hd95": summarize([float(r["hd95"]) for r in sub]),
                "asd": summarize([float(r["asd"]) for r in sub]),
                "volume_diff_percent": summarize_percent([float(r["volume_diff_percent"]) for r in sub]),
            }
        )
        full["methods"][method] = {
            "dice": mean_std([float(r["dice"]) for r in sub]),
            "unseen_dice": mean_std([float(r["dice_unseen_slices"]) for r in sub]),
            "hd95": mean_std([float(r["hd95"]) for r in sub]),
            "asd": mean_std([float(r["asd"]) for r in sub]),
            "volume_diff_percent": mean_std([float(r["volume_diff_percent"]) for r in sub]),
        }
    target = "train_calibrated_support_intersection_rule"
    for baseline in ["linear", "sdf_core", "support_100", "linear_core_intersection"]:
        full["paired_scan"][f"{target}_vs_{baseline}"] = paired(rows, target, baseline)
        full["paired_subject"][f"{target}_vs_{baseline}"] = paired(rows, target, baseline, subject_level=True)

    write_csv(osp.join(args.out_dir, "surface_summary_table.csv"), table)
    with open(osp.join(args.out_dir, "surface_summary.json"), "w") as f:
        json.dump(full, f, indent=2)
    print(json.dumps(full, indent=2))


if __name__ == "__main__":
    main()
