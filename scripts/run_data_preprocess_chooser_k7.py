#!/usr/bin/env python3
"""Train-set calibrated chooser between linear interpolation and SDF core.

This is a lightweight data-preprocessing refinement module. It does not use
test labels to tune the decision rule. The rule is calibrated on training cases
and then applied once to the held-out test cases.
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
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import run_sparse_prompt_core_envelope_workflow as wf
from run_traditional_linear_mask_interpolation_baseline import linear_mask_interpolation


def read_image(path: str):
    image = sitk.ReadImage(path)
    return sitk.GetArrayFromImage(image), image


def case_names(label_dir: str) -> list[str]:
    return [osp.basename(path).replace(".nii.gz", "") for path in sorted(glob(osp.join(label_dir, "*.nii.gz")))]


def summarize(values: list[float]) -> dict[str, float | int | None]:
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


def row_metrics(case_id: str, split: str, method: str, pred: np.ndarray, gt: np.ndarray, prompt: np.ndarray) -> dict:
    pzm = prompt_z_mask(prompt)
    ppv, rec = wf.precision_recall(pred, gt)
    gt_voxels = int(gt.sum())
    pred_voxels = int(pred.sum())
    return {
        "split": split,
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


def build_case(label_dir: str, case_id: str, split: str, k: int, strategy: str, profile: str) -> dict | None:
    gt_arr, gt_img = read_image(osp.join(label_dir, f"{case_id}.nii.gz"))
    gt = gt_arr > 0
    if not gt.any():
        return None
    selected_z = wf.select_sparse_slices(gt, int(k), strategy, case_id)
    prompt = wf.make_prompt(gt, selected_z)
    linear = linear_mask_interpolation(prompt)
    linear[prompt] = True

    oar = np.zeros_like(gt_arr, dtype=np.uint8)
    methods, support, n_candidates = wf.build_methods(prompt, selected_z, gt_img.GetSpacing(), oar, profile)
    core = methods["core_only"]
    envelope = methods["envelope"]
    oracle = core | (gt & (envelope & (~core)))
    oracle[prompt] = True

    agreement = wf.dice_score(core, linear)
    core_linear_vol_ratio = float(core.sum() / max(int(linear.sum()), 1))
    env_core_vol_ratio = float(envelope.sum() / max(int(core.sum()), 1))
    selected_z = np.asarray(selected_z, dtype=int)
    z_extent = int(selected_z[-1] - selected_z[0]) if selected_z.size else 0
    z_gap_mean = float(np.diff(selected_z).mean()) if selected_z.size > 1 else 0.0
    features = {
        "split": split,
        "case": case_id,
        "selected_z": ";".join(str(int(z)) for z in selected_z),
        "n_selected": int(selected_z.size),
        "z_extent": z_extent,
        "z_gap_mean": z_gap_mean,
        "core_linear_agreement": agreement,
        "core_linear_vol_ratio": core_linear_vol_ratio,
        "core_minus_linear_vol_percent": float((int(core.sum()) - int(linear.sum())) / max(int(linear.sum()), 1) * 100.0),
        "env_core_vol_ratio": env_core_vol_ratio,
        "core_better_than_linear": int(wf.dice_score(core, gt) > wf.dice_score(linear, gt)),
        "n_candidates": int(n_candidates),
    }
    preds = {
        "linear": linear,
        "sdf_core": core,
        "envelope": envelope,
        "oracle_envelope": oracle,
        "oracle_best_linear_core": core if wf.dice_score(core, gt) >= wf.dice_score(linear, gt) else linear,
    }
    metrics = [row_metrics(case_id, split, method, pred, gt, prompt) for method, pred in preds.items()]
    return {"features": features, "metrics": metrics, "preds": preds, "gt": gt, "prompt": prompt}


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
    return [float(vals.min() - 1e-6), *[float(v) for v in vals], *mids, float(vals.max() + 1e-6)]


def calibrate_threshold(train_features: list[dict], train_metric_by_case: dict[str, dict[str, float]]) -> dict:
    feature_name = "core_linear_vol_ratio"
    values = np.asarray([float(row[feature_name]) for row in train_features], dtype=float)
    best = None
    for threshold in threshold_candidates(values):
        for op in ("lt", "ge"):
            dice_values = []
            correct = []
            choose_core_count = 0
            for row in train_features:
                choose_core = float(row[feature_name]) < threshold if op == "lt" else float(row[feature_name]) >= threshold
                choose_core_count += int(choose_core)
                case = row["case"]
                method = "sdf_core" if choose_core else "linear"
                dice_values.append(float(train_metric_by_case[case][method]))
                correct.append(int(choose_core) == int(row["core_better_than_linear"]))
            candidate = {
                "feature": feature_name,
                "op": op,
                "threshold": float(threshold),
                "train_mean_dice": float(np.mean(dice_values)),
                "train_accuracy": float(np.mean(correct)),
                "train_choose_core": int(choose_core_count),
                "train_n": int(len(train_features)),
            }
            if best is None or candidate["train_mean_dice"] > best["train_mean_dice"]:
                best = candidate
    assert best is not None
    return best


def apply_chooser(features: list[dict], cases: dict[str, dict], rule: dict, split: str) -> list[dict]:
    rows = []
    for feat in features:
        value = float(feat[rule["feature"]])
        choose_core = value < float(rule["threshold"]) if rule["op"] == "lt" else value >= float(rule["threshold"])
        method = "sdf_core" if choose_core else "linear"
        case_data = cases[feat["case"]]
        pred = case_data["preds"][method]
        row = row_metrics(feat["case"], split, "train_calibrated_chooser", pred, case_data["gt"], case_data["prompt"])
        row["chosen_source"] = method
        row["chooser_feature_value"] = value
        rows.append(row)
    return rows


def grouped_metric(metrics: list[dict], split: str, method: str, metric: str = "dice") -> np.ndarray:
    return np.asarray([float(r[metric]) for r in metrics if r["split"] == split and r["method"] == method], dtype=float)


def paired_delta(metrics: list[dict], split: str, a: str, b: str) -> dict:
    by_case: dict[str, dict[str, float]] = {}
    for row in metrics:
        if row["split"] != split:
            continue
        by_case.setdefault(row["case"], {})[row["method"]] = float(row["dice"])
    delta = np.asarray([vals[a] - vals[b] for vals in by_case.values() if a in vals and b in vals], dtype=float)
    if delta.size == 0:
        return {"n": 0}
    try:
        p = float(wilcoxon(delta).pvalue) if np.any(np.abs(delta) > 1e-12) else 1.0
    except ValueError:
        p = 1.0
    return {
        "n": int(delta.size),
        "mean_delta": float(delta.mean()),
        "std_delta": float(delta.std()),
        "improved": int((delta > 0).sum()),
        "worse": int((delta < 0).sum()),
        "wilcoxon_p": p,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train-calibrated data preprocessing chooser for K=7.")
    parser.add_argument("--train_label_dir", default=osp.join(ROOT, "nnunet_runs/raw/Dataset015_CTV_Dataset004Split/labelsTr"))
    parser.add_argument("--test_label_dir", default=osp.join(ROOT, "nnunet_runs/raw/Dataset015_CTV_Dataset004Split/labelsTs"))
    parser.add_argument("--out_dir", default=osp.join(ROOT, "results/data_preprocess_chooser_k7_20260602"))
    parser.add_argument("--k", type=int, default=7)
    parser.add_argument("--strategy", default="even_nonempty")
    parser.add_argument("--profile", default="current")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    all_metrics: list[dict] = []
    all_features: list[dict] = []
    cases_by_split: dict[str, dict[str, dict]] = {"train": {}, "test": {}}
    skipped: list[dict] = []

    for split, label_dir in (("train", args.train_label_dir), ("test", args.test_label_dir)):
        for case_id in case_names(label_dir):
            data = build_case(label_dir, case_id, split, args.k, args.strategy, args.profile)
            if data is None:
                skipped.append({"split": split, "case": case_id, "reason": "empty target"})
                continue
            all_features.append(data["features"])
            all_metrics.extend(data["metrics"])
            cases_by_split[split][case_id] = data

    train_metric_by_case = {}
    for row in all_metrics:
        if row["split"] != "train":
            continue
        train_metric_by_case.setdefault(row["case"], {})[row["method"]] = float(row["dice"])
    train_features = [row for row in all_features if row["split"] == "train"]
    test_features = [row for row in all_features if row["split"] == "test"]
    rule = calibrate_threshold(train_features, train_metric_by_case)

    chooser_rows = []
    chooser_rows.extend(apply_chooser(train_features, cases_by_split["train"], rule, "train"))
    chooser_rows.extend(apply_chooser(test_features, cases_by_split["test"], rule, "test"))
    all_metrics.extend(chooser_rows)

    write_csv(osp.join(args.out_dir, "features.csv"), all_features)
    write_csv(osp.join(args.out_dir, "per_case_metrics.csv"), all_metrics)

    summary = {
        "config": {"k": args.k, "strategy": args.strategy, "profile": args.profile},
        "skipped": skipped,
        "rule": rule,
        "methods": {},
        "paired": {},
    }
    for split in ("train", "test"):
        summary["methods"][split] = {}
        for method in sorted({r["method"] for r in all_metrics if r["split"] == split}):
            vals = [float(r["dice"]) for r in all_metrics if r["split"] == split and r["method"] == method]
            unseen = [float(r["dice_unseen_slices"]) for r in all_metrics if r["split"] == split and r["method"] == method]
            summary["methods"][split][method] = {"dice": summarize(vals), "unseen_dice": summarize(unseen)}
        summary["paired"][split] = {
            "chooser_vs_linear": paired_delta(all_metrics, split, "train_calibrated_chooser", "linear"),
            "chooser_vs_sdf_core": paired_delta(all_metrics, split, "train_calibrated_chooser", "sdf_core"),
            "sdf_core_vs_linear": paired_delta(all_metrics, split, "sdf_core", "linear"),
            "oracle_best_vs_linear": paired_delta(all_metrics, split, "oracle_best_linear_core", "linear"),
            "oracle_best_vs_sdf_core": paired_delta(all_metrics, split, "oracle_best_linear_core", "sdf_core"),
        }
    with open(osp.join(args.out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    print("Wrote", osp.join(args.out_dir, "features.csv"))
    print("Wrote", osp.join(args.out_dir, "per_case_metrics.csv"))
    print("Wrote", osp.join(args.out_dir, "summary.json"))


if __name__ == "__main__":
    main()
