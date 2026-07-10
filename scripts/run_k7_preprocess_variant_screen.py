#!/usr/bin/env python3
"""Screen deployable K=7 data-preprocessing refinement variants.

The script uses training labels only to choose a fixed preprocessing variant
or a one-threshold feature rule. Test labels are used only for final reporting.
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
from scipy.stats import wilcoxon


ROOT = str(Path(__file__).resolve().parents[1])
SCRIPT_DIR = osp.join(ROOT, "scripts")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import run_sparse_prompt_core_envelope_workflow as wf
from run_traditional_linear_mask_interpolation_baseline import linear_mask_interpolation
from utils.rules import threshold_condition


FEATURES = [
    "core_linear_vol_ratio",
    "base_linear_vol_ratio",
    "core_base_vol_ratio",
    "core_linear_agreement",
    "base_linear_agreement",
    "z_extent",
    "z_gap_mean",
    "prompt_area_cv",
    "prompt_endpoint_mean_ratio",
    "prompt_area_slope_ratio",
]


def read_label(path: str):
    image = sitk.ReadImage(path)
    return sitk.GetArrayFromImage(image) > 0, image


def case_names(label_dir: str) -> list[str]:
    return [osp.basename(p).replace(".nii.gz", "") for p in sorted(glob(osp.join(label_dir, "*.nii.gz")))]


def subject_id(case_id: str) -> str:
    return case_id.split("_CT", 1)[0]


def summarize(values: list[float]) -> dict:
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


def metric_row(split: str, case_id: str, method: str, pred: np.ndarray, gt: np.ndarray, prompt: np.ndarray) -> dict:
    pzm = prompt_z_mask(prompt)
    ppv, rec = wf.precision_recall(pred, gt)
    gt_voxels = int(gt.sum())
    pred_voxels = int(pred.sum())
    return {
        "split": split,
        "subject": subject_id(case_id),
        "case": case_id,
        "method": method,
        "dice": wf.dice_score(pred, gt),
        "dice_unseen_slices": wf.dice_score(pred[~pzm], gt[~pzm]) if (~pzm).any() else float("nan"),
        "precision": ppv,
        "recall": rec,
        "gt_voxels": gt_voxels,
        "pred_voxels": pred_voxels,
        "volume_diff_percent": float((pred_voxels - gt_voxels) / gt_voxels * 100.0) if gt_voxels > 0 else float("nan"),
    }


def support_mask(support: np.ndarray, threshold: float, prompt: np.ndarray) -> np.ndarray:
    mask = support >= float(threshold)
    mask[prompt] = True
    mask = wf.keep_seed_connected(mask, prompt)
    mask[prompt] = True
    return mask.astype(bool)


def volume_match_support(support_masks: dict[str, np.ndarray], target_volume: int) -> np.ndarray:
    name = min(support_masks, key=lambda k: abs(int(support_masks[k].sum()) - int(target_volume)))
    return support_masks[name]


def prompt_shape_features(gt: np.ndarray, selected_z: np.ndarray) -> dict:
    areas = np.asarray([gt[int(z)].sum() for z in selected_z], dtype=float)
    mean = float(areas.mean()) if areas.size else 0.0
    denom = max(mean, 1.0)
    if areas.size > 1:
        slope = float((areas[-1] - areas[0]) / denom)
        diff_abs = float(np.abs(np.diff(areas)).mean() / denom)
    else:
        slope = 0.0
        diff_abs = 0.0
    endpoint_mean = float(((areas[0] + areas[-1]) / 2.0) / denom) if areas.size else 0.0
    return {
        "prompt_area_mean": mean,
        "prompt_area_cv": float(areas.std() / denom) if areas.size else 0.0,
        "prompt_endpoint_mean_ratio": endpoint_mean,
        "prompt_area_slope_ratio": slope,
        "prompt_area_diff_abs_mean_ratio": diff_abs,
    }


def build_case(label_dir: str, case_id: str, split: str, k: int, strategy: str, profile: str):
    gt, gt_img = read_label(osp.join(label_dir, f"{case_id}.nii.gz"))
    if not gt.any():
        return None

    selected_z = wf.select_sparse_slices(gt, int(k), strategy, case_id)
    prompt = wf.make_prompt(gt, selected_z)
    linear = linear_mask_interpolation(prompt).astype(bool)
    linear[prompt] = True

    oar = np.zeros_like(gt, dtype=np.uint8)
    methods, support, n_candidates = wf.build_methods(prompt, selected_z, gt_img.GetSpacing(), oar, profile)
    base = methods["sdf_base"].astype(bool)
    core = methods["core_only"].astype(bool)
    envelope = methods["envelope"].astype(bool)

    support_masks = {
        f"support_{int(t * 100):03d}": support_mask(support, t, prompt)
        for t in (1.0, 0.8, 0.6, 0.4, 0.2)
    }
    union = (linear | core)
    union[prompt] = True
    inter = (linear & core)
    inter[prompt] = True
    vote2_lcb = ((linear.astype(np.uint8) + core.astype(np.uint8) + base.astype(np.uint8)) >= 2)
    vote2_lcb[prompt] = True
    vote2_lce = ((linear.astype(np.uint8) + core.astype(np.uint8) + envelope.astype(np.uint8)) >= 2)
    vote2_lce[prompt] = True

    preds = {
        "linear": linear,
        "sdf_base": base,
        "sdf_core": core,
        "envelope": envelope,
        "linear_core_union": union,
        "linear_core_intersection": inter,
        "vote2_linear_core_base": vote2_lcb,
        "vote2_linear_core_envelope": vote2_lce,
        "support_volume_match_linear": volume_match_support(support_masks, int(linear.sum())),
        "support_volume_match_mean_linear_core": volume_match_support(support_masks, int((int(linear.sum()) + int(core.sum())) / 2)),
        **support_masks,
    }
    metrics = [metric_row(split, case_id, method, pred, gt, prompt) for method, pred in preds.items()]

    selected_z = np.asarray(selected_z, dtype=int)
    shape = prompt_shape_features(gt, selected_z)
    features = {
        "split": split,
        "subject": subject_id(case_id),
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
    return features, metrics


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


def threshold_candidates(values: np.ndarray) -> list[float]:
    vals = np.unique(values.astype(float))
    if vals.size == 0:
        return [0.0]
    mids = ((vals[:-1] + vals[1:]) / 2.0).tolist()
    return [float(vals.min() - 1e-6), *[float(v) for v in vals], *[float(v) for v in mids], float(vals.max() + 1e-6)]


def metric_lookup(rows: list[dict], split: str) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        if row["split"] != split:
            continue
        out.setdefault(row["case"], {})[row["method"]] = row
    return out


def calibrate_best_fixed(train_metrics: list[dict]) -> dict:
    methods = sorted({r["method"] for r in train_metrics if r["split"] == "train"})
    best = None
    for method in methods:
        vals = [float(r["dice"]) for r in train_metrics if r["split"] == "train" and r["method"] == method]
        cand = {"type": "fixed", "method": method, "train_mean_dice": float(np.mean(vals))}
        if best is None or cand["train_mean_dice"] > best["train_mean_dice"]:
            best = cand
    assert best is not None
    return best


def calibrate_best_threshold_rule(train_features: list[dict], train_metrics: list[dict]) -> dict:
    methods = sorted({r["method"] for r in train_metrics if r["split"] == "train"})
    lookup = metric_lookup(train_metrics, "train")
    best = None
    for feature in FEATURES:
        values = np.asarray([float(r[feature]) for r in train_features], dtype=float)
        for threshold in threshold_candidates(values):
            for op in ("lt", "ge"):
                for method_a in methods:
                    for method_b in methods:
                        if method_a == method_b:
                            continue
                        vals = []
                        choose_a = 0
                        for feat in train_features:
                            cond = threshold_condition(float(feat[feature]), op, threshold)
                            method = method_a if cond else method_b
                            choose_a += int(cond)
                            vals.append(float(lookup[feat["case"]][method]["dice"]))
                        cand = {
                            "type": "threshold",
                            "feature": feature,
                            "op": op,
                            "threshold": float(threshold),
                            "method_if_true": method_a,
                            "method_if_false": method_b,
                            "train_mean_dice": float(np.mean(vals)),
                            "train_choose_true": int(choose_a),
                            "train_n": int(len(train_features)),
                        }
                        if best is None or cand["train_mean_dice"] > best["train_mean_dice"]:
                            best = cand
    assert best is not None
    return best


def apply_rule(features: list[dict], lookup: dict[str, dict[str, dict]], rule: dict, name: str) -> list[dict]:
    rows = []
    for feat in features:
        if rule["type"] == "fixed":
            method = rule["method"]
        else:
            cond = threshold_condition(float(feat[rule["feature"]]), str(rule["op"]), float(rule["threshold"]))
            method = rule["method_if_true"] if cond else rule["method_if_false"]
        row = dict(lookup[feat["case"]][method])
        row["method"] = name
        row["chosen_source"] = method
        rows.append(row)
    return rows


def paired(rows: list[dict], split: str, a: str, b: str, subject_level: bool = False) -> dict:
    key = "subject" if subject_level else "case"
    by_key: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        if row["split"] != split:
            continue
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


def summarize_methods(rows: list[dict], split: str) -> dict:
    out = {}
    for method in sorted({r["method"] for r in rows if r["split"] == split}):
        sub = [r for r in rows if r["split"] == split and r["method"] == method]
        out[method] = {
            "dice": summarize([float(r["dice"]) for r in sub]),
            "unseen_dice": summarize([float(r["dice_unseen_slices"]) for r in sub]),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="K=7 sparse-prompt preprocessing screen on local target-label folders.")
    parser.add_argument("--train_label_dir", required=True, help="Local training target-label directory.")
    parser.add_argument("--test_label_dir", required=True, help="Local test target-label directory.")
    parser.add_argument("--out_dir", default=osp.join(ROOT, "results/data_preprocess_variant_screen_k7_20260602"))
    parser.add_argument("--k", type=int, default=7)
    parser.add_argument("--strategy", default="even_nonempty")
    parser.add_argument("--profile", default="current")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    features: list[dict] = []
    metrics: list[dict] = []
    skipped: list[dict] = []
    for split, label_dir in (("train", args.train_label_dir), ("test", args.test_label_dir)):
        for idx, case_id in enumerate(case_names(label_dir), start=1):
            result = build_case(label_dir, case_id, split, args.k, args.strategy, args.profile)
            if result is None:
                skipped.append({"split": split, "case": case_id, "reason": "empty target"})
                continue
            feat, rows = result
            features.append(feat)
            metrics.extend(rows)
            print(f"{split} {idx:03d} {case_id}", flush=True)

    train_features = [r for r in features if r["split"] == "train"]
    test_features = [r for r in features if r["split"] == "test"]
    train_lookup = metric_lookup(metrics, "train")
    test_lookup = metric_lookup(metrics, "test")
    fixed_rule = calibrate_best_fixed(metrics)
    threshold_rule = calibrate_best_threshold_rule(train_features, metrics)

    final_rows = list(metrics)
    final_rows.extend(apply_rule(train_features, train_lookup, fixed_rule, "train_calibrated_fixed_best"))
    final_rows.extend(apply_rule(test_features, test_lookup, fixed_rule, "train_calibrated_fixed_best"))
    final_rows.extend(apply_rule(train_features, train_lookup, threshold_rule, "train_calibrated_threshold_rule"))
    final_rows.extend(apply_rule(test_features, test_lookup, threshold_rule, "train_calibrated_threshold_rule"))

    write_csv(osp.join(args.out_dir, "features.csv"), features)
    write_csv(osp.join(args.out_dir, "per_case_metrics.csv"), final_rows)

    summary = {
        "config": {"k": args.k, "strategy": args.strategy, "profile": args.profile},
        "skipped": skipped,
        "fixed_rule": fixed_rule,
        "threshold_rule": threshold_rule,
        "methods": {"train": summarize_methods(final_rows, "train"), "test": summarize_methods(final_rows, "test")},
        "paired_test_scan": {
            "threshold_vs_linear": paired(final_rows, "test", "train_calibrated_threshold_rule", "linear"),
            "threshold_vs_sdf_core": paired(final_rows, "test", "train_calibrated_threshold_rule", "sdf_core"),
            "fixed_vs_linear": paired(final_rows, "test", "train_calibrated_fixed_best", "linear"),
            "fixed_vs_sdf_core": paired(final_rows, "test", "train_calibrated_fixed_best", "sdf_core"),
        },
        "paired_test_subject": {
            "threshold_vs_linear": paired(final_rows, "test", "train_calibrated_threshold_rule", "linear", subject_level=True),
            "threshold_vs_sdf_core": paired(final_rows, "test", "train_calibrated_threshold_rule", "sdf_core", subject_level=True),
            "fixed_vs_linear": paired(final_rows, "test", "train_calibrated_fixed_best", "linear", subject_level=True),
            "fixed_vs_sdf_core": paired(final_rows, "test", "train_calibrated_fixed_best", "sdf_core", subject_level=True),
        },
    }
    with open(osp.join(args.out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(osp.join(args.out_dir, "selected_threshold_rule.json"), "w") as f:
        json.dump(threshold_rule, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
