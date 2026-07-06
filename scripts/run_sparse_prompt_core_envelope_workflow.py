#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import math
import os
import os.path as osp
from pathlib import Path
from collections import defaultdict
from glob import glob
from itertools import product

import numpy as np
import SimpleITK as sitk
from scipy import ndimage


ROOT = str(Path(__file__).resolve().parents[1])


PROFILES = {
    "current": {
        "candidate_shrink": [0.6, 0.8, 1.0, 1.2, 1.4],
        "level_mm": [0.0],
        "endpoint_plateau_mm": [0.0],
        "core_threshold": 0.80,
        "envelope_threshold": 0.20,
    },
    "mild_expanded": {
        "candidate_shrink": [0.7, 1.0, 1.3],
        "level_mm": [2.0, 0.0, -3.0, -6.0],
        "endpoint_plateau_mm": [0.0],
        "core_threshold": 0.65,
        "envelope_threshold": 0.15,
    },
    "endpoint_plateau": {
        "candidate_shrink": [0.8, 1.0, 1.2],
        "level_mm": [0.0, -4.0],
        "endpoint_plateau_mm": [0.0, 8.0],
        "core_threshold": 0.65,
        "envelope_threshold": 0.15,
    },
    "high_recall": {
        "candidate_shrink": [0.6, 1.0, 1.4],
        "level_mm": [0.0, -6.0, -12.0],
        "endpoint_plateau_mm": [0.0, 10.0],
        "core_threshold": 0.60,
        "envelope_threshold": 0.10,
    },
}


def read_image(path):
    image = sitk.ReadImage(path)
    return sitk.GetArrayFromImage(image), image


def write_like(arr, ref_image, path, dtype=None):
    if dtype is not None:
        arr = arr.astype(dtype)
    out = sitk.GetImageFromArray(arr)
    out.CopyInformation(ref_image)
    sitk.WriteImage(out, path)


def signed_distance_2d(mask2d, spacing_yx):
    mask2d = mask2d.astype(bool)
    if not mask2d.any():
        return np.full(mask2d.shape, -1e6, dtype=np.float32)
    inside = ndimage.distance_transform_edt(mask2d, sampling=spacing_yx)
    outside = ndimage.distance_transform_edt(~mask2d, sampling=spacing_yx)
    return (inside - outside).astype(np.float32)


def sparse_sdf(prompt, spacing_xyz, shrink_per_mm=1.0, endpoint_plateau_mm=0.0):
    prompt = prompt.astype(bool)
    z_indices = np.where(prompt.reshape(prompt.shape[0], -1).any(axis=1))[0]
    if z_indices.size == 0:
        return np.full(prompt.shape, -1e6, dtype=np.float32), z_indices

    spacing_x, spacing_y, spacing_z = [float(v) for v in spacing_xyz]
    spacing_yx = (spacing_y, spacing_x)
    sdfs = {int(z): signed_distance_2d(prompt[int(z)], spacing_yx) for z in z_indices}
    out = np.full(prompt.shape, -1e6, dtype=np.float32)
    plateau = max(float(endpoint_plateau_mm), 0.0)

    for z in range(prompt.shape[0]):
        if z in sdfs:
            sdf = sdfs[int(z)]
        elif z < z_indices[0]:
            dz_mm = float(z_indices[0] - z) * spacing_z
            eff_dz = max(dz_mm - plateau, 0.0)
            sdf = sdfs[int(z_indices[0])] - float(shrink_per_mm) * eff_dz
        elif z > z_indices[-1]:
            dz_mm = float(z - z_indices[-1]) * spacing_z
            eff_dz = max(dz_mm - plateau, 0.0)
            sdf = sdfs[int(z_indices[-1])] - float(shrink_per_mm) * eff_dz
        else:
            right = int(np.searchsorted(z_indices, z))
            z0 = int(z_indices[right - 1])
            z1 = int(z_indices[right])
            t = float(z - z0) / max(float(z1 - z0), 1.0)
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


def precision_recall(pred, gt):
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    inter = int(np.logical_and(pred, gt).sum())
    precision = float(inter / max(int(pred.sum()), 1))
    recall = float(inter / max(int(gt.sum()), 1))
    return precision, recall


def surface_metrics(pred, gt, spacing_xyz):
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    if not pred.any() and not gt.any():
        return 0.0, 0.0
    if not pred.any() or not gt.any():
        return float("nan"), float("nan")
    pts = np.argwhere(pred | gt)
    spacing_zyx = np.asarray(spacing_xyz[::-1], dtype=float)
    pad = np.ceil(20.0 / np.maximum(spacing_zyx, 1e-6)).astype(int)
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


def case_names(gt_dir):
    return [osp.basename(path).replace(".nii.gz", "") for path in sorted(glob(osp.join(gt_dir, "*.nii.gz")))]


def fill_to_k(selected, available, k):
    selected = sorted(set(int(v) for v in selected))
    available = np.asarray(sorted(set(int(v) for v in available)), dtype=int)
    if len(selected) >= k:
        return np.asarray(selected[:k], dtype=int)
    while len(selected) < k and len(selected) < len(available):
        if not selected:
            selected.append(int(available[len(available) // 2]))
            continue
        dist = np.min(np.abs(available[:, None] - np.asarray(selected)[None, :]), axis=1)
        order = np.argsort(dist)[::-1]
        added = False
        for idx in order:
            cand = int(available[idx])
            if cand not in selected:
                selected.append(cand)
                added = True
                break
        if not added:
            break
    return np.asarray(sorted(set(selected)), dtype=int)


def quantile_slices(available, k, quantiles):
    z = np.asarray(available, dtype=int)
    idx = np.clip(np.round(np.asarray(quantiles) * (len(z) - 1)).astype(int), 0, len(z) - 1)
    return fill_to_k(z[idx], z, k)


def select_sparse_slices(gt, k, strategy, case_id):
    z_available = np.where(gt.reshape(gt.shape[0], -1).any(axis=1))[0]
    if z_available.size == 0:
        return np.asarray([], dtype=int)
    if z_available.size <= k:
        return z_available.astype(int)

    areas = gt.reshape(gt.shape[0], -1).sum(axis=1)
    first = int(z_available[0])
    last = int(z_available[-1])
    center = int(z_available[len(z_available) // 2])
    max_area = int(z_available[np.argmax(areas[z_available])])

    if strategy == "even_nonempty":
        return quantile_slices(z_available, k, np.linspace(0.0, 1.0, int(k)))
    if strategy == "max_area_anchors":
        return fill_to_k([first, max_area, last], z_available, k)
    if strategy == "central":
        mid = len(z_available) // 2
        half = int(k) // 2
        lo = max(0, mid - half)
        hi = min(len(z_available), lo + int(k))
        lo = max(0, hi - int(k))
        return fill_to_k(z_available[lo:hi], z_available, k)
    if strategy == "boundary_focused":
        if int(k) == 1:
            return np.asarray([max_area], dtype=int)
        q = (1.0 - np.cos(np.pi * np.arange(int(k)) / max(int(k) - 1, 1))) / 2.0
        return quantile_slices(z_available, k, q)
    if strategy == "random_seeded":
        digest = hashlib.md5(f"{case_id}-{k}-{strategy}".encode("utf-8")).hexdigest()
        seed = int(digest[:8], 16)
        rng = np.random.default_rng(seed)
        return np.asarray(sorted(rng.choice(z_available, size=int(k), replace=False).tolist()), dtype=int)
    if strategy == "first_center_last":
        return fill_to_k([first, center, last], z_available, k)
    raise ValueError(f"Unknown prompt strategy: {strategy}")


def make_prompt(gt, selected_z):
    prompt = np.zeros(gt.shape, dtype=bool)
    for z in selected_z:
        prompt[int(z)] = gt[int(z)]
    return prompt


def keep_seed_connected(mask, seed):
    mask = mask.astype(bool)
    seed = seed.astype(bool)
    if not mask.any() or not seed.any():
        return mask
    labeled, _ = ndimage.label(mask)
    ids = np.unique(labeled[seed])
    ids = ids[ids > 0]
    if ids.size == 0:
        return mask
    return np.isin(labeled, ids)


def profile_candidates(profile_name):
    profile = PROFILES[profile_name]
    candidates = []
    for shrink, level_mm, plateau_mm in product(
        profile["candidate_shrink"], profile["level_mm"], profile["endpoint_plateau_mm"]
    ):
        candidates.append(
            {
                "shrink": float(shrink),
                "level_mm": float(level_mm),
                "endpoint_plateau_mm": float(plateau_mm),
            }
        )
    base = {"shrink": 1.0, "level_mm": 0.0, "endpoint_plateau_mm": 0.0}
    if base not in candidates:
        candidates.append(base)
    return candidates


def build_methods(prompt, selected_z, spacing_xyz, oar, profile_name):
    profile = PROFILES[profile_name]
    candidates = profile_candidates(profile_name)
    support_count = np.zeros(prompt.shape, dtype=np.uint16)
    base = None
    for spec in candidates:
        sdf, _ = sparse_sdf(
            prompt,
            spacing_xyz,
            shrink_per_mm=spec["shrink"],
            endpoint_plateau_mm=spec["endpoint_plateau_mm"],
        )
        pred = sdf >= spec["level_mm"]
        pred[selected_z] = prompt[selected_z]
        pred = pred.astype(bool)
        support_count += pred.astype(np.uint16)
        if spec == {"shrink": 1.0, "level_mm": 0.0, "endpoint_plateau_mm": 0.0}:
            base = pred.copy()
    if base is None:
        sdf, _ = sparse_sdf(prompt, spacing_xyz, shrink_per_mm=1.0, endpoint_plateau_mm=0.0)
        base = sdf >= 0.0
        base[selected_z] = prompt[selected_z]
        base = base.astype(bool)

    support = support_count.astype(np.float32) / max(len(candidates), 1)
    core = support >= float(profile["core_threshold"])
    envelope = support >= float(profile["envelope_threshold"])
    core &= envelope
    core[prompt] = True
    envelope[prompt] = True

    spinal = oar == 3
    envelope_oar = envelope.copy()
    envelope_oar[spinal] = False
    envelope_oar[prompt] = True
    core_oar = core & envelope_oar
    core_oar[prompt] = True

    support_majority = support >= 0.5
    support_majority &= envelope_oar
    support_majority[prompt] = True
    support_majority = keep_seed_connected(support_majority, prompt | core_oar)
    support_majority[prompt] = True

    base_oar = base.copy()
    base_oar[spinal] = False
    base_oar[prompt] = True
    base_oar = keep_seed_connected(base_oar, prompt)
    base_oar[prompt] = True

    return {
        "sdf_base": base,
        "sdf_base_oar": base_oar,
        "core_only": core_oar,
        "support_majority_oar": support_majority,
        "envelope": envelope_oar,
        "oracle_upper_bound": None,
    }, support, len(candidates)


def metric_row(config, case_id, method, pred, gt, prompt_z_mask, spacing_xyz, skip_surface_metrics):
    if skip_surface_metrics:
        hd95, asd = float("nan"), float("nan")
    else:
        hd95, asd = surface_metrics(pred, gt, spacing_xyz)
    ppv, rec = precision_recall(pred, gt)
    gt_volume = int(gt.sum())
    pred_volume = int(pred.sum())
    return {
        **config,
        "case": case_id,
        "method": method,
        "dice": dice_score(pred, gt),
        "dice_prompt_slices": dice_score(pred[prompt_z_mask], gt[prompt_z_mask]) if prompt_z_mask.any() else float("nan"),
        "dice_unseen_slices": dice_score(pred[~prompt_z_mask], gt[~prompt_z_mask]) if (~prompt_z_mask).any() else float("nan"),
        "precision": ppv,
        "recall": rec,
        "hd95": hd95,
        "asd": asd,
        "gt_voxels": gt_volume,
        "pred_voxels": pred_volume,
        "volume_diff_voxels": pred_volume - gt_volume,
        "volume_diff_percent": float((pred_volume - gt_volume) / gt_volume * 100.0) if gt_volume > 0 else float("nan"),
    }


def config_name(config):
    return f"{config['profile']}__k{config['k']}__{config['strategy']}"


def run_configs(args, configs, out_dir, skip_surface_metrics=True, write_predictions=False):
    rows = []
    skipped = []
    os.makedirs(out_dir, exist_ok=True)
    cases = case_names(args.gt_dir)
    if args.case:
        keep = set(args.case)
        cases = [case for case in cases if case in keep]

    for case_index, case_id in enumerate(cases, start=1):
        print(f"[{case_index}/{len(cases)}] {case_id}", flush=True)
        ct_path = osp.join(args.ct_dir, f"{case_id}_0000.nii.gz")
        gt_path = osp.join(args.gt_dir, f"{case_id}.nii.gz")
        oar_path = osp.join(args.oar_dir, f"{case_id}.nii.gz")
        if not (osp.exists(ct_path) and osp.exists(gt_path) and osp.exists(oar_path)):
            skipped.append({"case": case_id, "reason": "missing input"})
            continue
        gt_arr, gt_img = read_image(gt_path)
        oar, _ = read_image(oar_path)
        if gt_arr.shape != oar.shape:
            skipped.append({"case": case_id, "reason": f"shape mismatch gt={gt_arr.shape} oar={oar.shape}"})
            continue
        gt = gt_arr == int(args.target_label)
        if not gt.any():
            skipped.append({"case": case_id, "reason": "empty target"})
            continue
        spacing_xyz = gt_img.GetSpacing()

        prompt_cache = {}
        for config in configs:
            prompt_key = (int(config["k"]), config["strategy"])
            if prompt_key not in prompt_cache:
                selected_z = select_sparse_slices(gt, int(config["k"]), config["strategy"], case_id)
                prompt = make_prompt(gt, selected_z)
                prompt_z_mask = np.zeros(gt.shape[0], dtype=bool)
                prompt_z_mask[selected_z] = True
                prompt_cache[prompt_key] = (prompt, selected_z, prompt_z_mask)
            prompt, selected_z, prompt_z_mask = prompt_cache[prompt_key]

            methods, support, n_candidates = build_methods(prompt, selected_z, spacing_xyz, oar, config["profile"])
            core = methods["core_only"]
            envelope = methods["envelope"]
            oracle = core | (gt & (envelope & (~core)))
            oracle[prompt] = True
            methods["oracle_upper_bound"] = oracle

            local_config = dict(config)
            local_config["selected_z"] = ";".join(str(int(z)) for z in selected_z)
            local_config["n_selected"] = int(len(selected_z))
            local_config["n_candidates"] = int(n_candidates)
            local_config["core_threshold"] = float(PROFILES[config["profile"]]["core_threshold"])
            local_config["envelope_threshold"] = float(PROFILES[config["profile"]]["envelope_threshold"])

            for method, pred in methods.items():
                row = metric_row(
                    local_config,
                    case_id,
                    method,
                    pred,
                    gt,
                    prompt_z_mask,
                    spacing_xyz,
                    skip_surface_metrics=skip_surface_metrics,
                )
                if write_predictions:
                    pred_dir = osp.join(out_dir, "predictions", config_name(config), method)
                    os.makedirs(pred_dir, exist_ok=True)
                    pred_path = osp.join(pred_dir, f"{case_id}.nii.gz")
                    write_like(pred.astype(np.uint8), gt_img, pred_path, dtype=np.uint8)
                    row["prediction_path"] = pred_path
                rows.append(row)

    return rows, skipped


def write_csv(path, rows):
    os.makedirs(osp.dirname(path), exist_ok=True)
    if not rows:
        with open(path, "w", newline="") as f:
            f.write("")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_summary(rows):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = (row["profile"], int(row["k"]), row["strategy"], row["method"])
        for metric in (
            "dice",
            "dice_prompt_slices",
            "dice_unseen_slices",
            "precision",
            "recall",
            "hd95",
            "asd",
            "volume_diff_percent",
        ):
            value = row.get(metric, float("nan"))
            if isinstance(value, float) and math.isnan(value):
                continue
            grouped[key][metric].append(value)

    summary_rows = []
    for (profile, k, strategy, method), values in sorted(grouped.items()):
        row = {"profile": profile, "k": k, "strategy": strategy, "method": method}
        n = 0
        for metric, metric_values in values.items():
            stat = summarize(metric_values)
            row[f"{metric}_mean"] = stat["mean"]
            row[f"{metric}_std"] = stat["std"]
            row[f"{metric}_n"] = stat["n"]
            n = max(n, int(stat["n"]))
        row["n_cases"] = n
        summary_rows.append(row)
    return summary_rows


def make_ranking(summary_rows):
    by_config = defaultdict(dict)
    for row in summary_rows:
        key = (row["profile"], int(row["k"]), row["strategy"])
        by_config[key][row["method"]] = row

    ranking = []
    for (profile, k, strategy), methods in by_config.items():
        core = methods.get("core_only", {})
        envelope = methods.get("envelope", {})
        oracle = methods.get("oracle_upper_bound", {})
        sdf = methods.get("sdf_base", {})
        row = {
            "profile": profile,
            "k": k,
            "strategy": strategy,
            "sdf_base_dice": sdf.get("dice_mean", ""),
            "core_dice": core.get("dice_mean", ""),
            "core_precision": core.get("precision_mean", ""),
            "core_recall": core.get("recall_mean", ""),
            "envelope_dice": envelope.get("dice_mean", ""),
            "envelope_precision": envelope.get("precision_mean", ""),
            "envelope_recall": envelope.get("recall_mean", ""),
            "oracle_dice": oracle.get("dice_mean", ""),
            "oracle_unseen_dice": oracle.get("dice_unseen_slices_mean", ""),
            "core_gain_vs_sdf": "",
            "oracle_gain_vs_core": "",
            "oracle_gain_vs_sdf": "",
        }
        if row["core_dice"] != "" and row["sdf_base_dice"] != "":
            row["core_gain_vs_sdf"] = float(row["core_dice"]) - float(row["sdf_base_dice"])
        if row["oracle_dice"] != "" and row["core_dice"] != "":
            row["oracle_gain_vs_core"] = float(row["oracle_dice"]) - float(row["core_dice"])
        if row["oracle_dice"] != "" and row["sdf_base_dice"] != "":
            row["oracle_gain_vs_sdf"] = float(row["oracle_dice"]) - float(row["sdf_base_dice"])
        ranking.append(row)

    def sort_key(row):
        oracle_gain = row["oracle_gain_vs_core"]
        core_dice = row["core_dice"]
        envelope_recall = row["envelope_recall"]
        return (
            float(oracle_gain) if oracle_gain != "" else -1.0,
            float(envelope_recall) if envelope_recall != "" else -1.0,
            float(core_dice) if core_dice != "" else -1.0,
        )

    return sorted(ranking, key=sort_key, reverse=True)


def write_outputs(out_dir, rows, skipped, args):
    per_case_csv = osp.join(out_dir, "per_case_metrics.csv")
    summary_csv = osp.join(out_dir, "summary.csv")
    ranking_csv = osp.join(out_dir, "oracle_gain_ranking.csv")
    summary_json = osp.join(out_dir, "summary.json")

    summary_rows = make_summary(rows)
    ranking = make_ranking(summary_rows)
    write_csv(per_case_csv, rows)
    write_csv(summary_csv, summary_rows)
    write_csv(ranking_csv, ranking)
    with open(summary_json, "w") as f:
        json.dump(
            {
                "out_dir": out_dir,
                "num_rows": len(rows),
                "num_configs": len(set((r["profile"], int(r["k"]), r["strategy"]) for r in rows)),
                "skipped": skipped,
                "profiles": {name: PROFILES[name] for name in args.profiles},
            },
            f,
            indent=2,
        )
    print("Wrote", per_case_csv)
    print("Wrote", summary_csv)
    print("Wrote", ranking_csv)
    print("Wrote", summary_json)
    print("Top oracle-gain configs:")
    for row in ranking[:10]:
        print(
            f"  {row['profile']} k={row['k']} {row['strategy']}: "
            f"core={row['core_dice']:.4f} oracle={row['oracle_dice']:.4f} "
            f"gain={row['oracle_gain_vs_core']:.4f} env_recall={row['envelope_recall']:.4f}"
        )
    return summary_rows, ranking


def configs_from_args(args):
    return [
        {"profile": profile, "k": int(k), "strategy": strategy}
        for profile, k, strategy in product(args.profiles, args.k_values, args.strategies)
    ]


def configs_from_ranking(ranking, n):
    configs = []
    seen = set()
    for row in ranking:
        key = (row["profile"], int(row["k"]), row["strategy"])
        if key in seen:
            continue
        seen.add(key)
        configs.append({"profile": row["profile"], "k": int(row["k"]), "strategy": row["strategy"]})
        if len(configs) >= int(n):
            break
    return configs


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Automated sparse-prompt CTV workflow for K sensitivity, prompt strategy, "
            "and core-envelope candidate-envelope screening."
        )
    )
    parser.add_argument("--ct_dir", required=True, help="Local CT image directory, for example /path/to/local_dataset/imagesTs.")
    parser.add_argument("--gt_dir", required=True, help="Local target-label directory, for example /path/to/local_dataset/labelsTs.")
    parser.add_argument("--oar_dir", required=True, help="Local OAR mask directory aligned with --ct_dir and --gt_dir.")
    parser.add_argument("--out_root", default=osp.join(ROOT, "results/next_sparse_prompt_core_envelope_workflow"))
    parser.add_argument("--target_label", type=int, default=1)
    parser.add_argument("--k_values", nargs="+", type=int, default=[3, 5, 7, 9])
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=["even_nonempty", "max_area_anchors", "boundary_focused"],
        choices=["even_nonempty", "max_area_anchors", "central", "boundary_focused", "random_seeded", "first_center_last"],
    )
    parser.add_argument("--profiles", nargs="+", default=["current", "mild_expanded", "endpoint_plateau", "high_recall"], choices=sorted(PROFILES))
    parser.add_argument("--case", action="append", default=None)
    parser.add_argument("--skip_surface_metrics", action="store_true", help="Skip HD95/ASD for the screening stage.")
    parser.add_argument("--full_top_n", type=int, default=0, help="Rerun the top-N oracle-gain configs with HD95/ASD.")
    parser.add_argument("--write_top_predictions", action="store_true", help="Save masks for the full top-N rerun.")
    args = parser.parse_args()

    configs = configs_from_args(args)
    screen_dir = osp.join(args.out_root, "screen")
    print(f"Screening {len(configs)} configs")
    screen_rows, screen_skipped = run_configs(
        args,
        configs,
        screen_dir,
        skip_surface_metrics=bool(args.skip_surface_metrics),
        write_predictions=False,
    )
    _, ranking = write_outputs(screen_dir, screen_rows, screen_skipped, args)

    if int(args.full_top_n) > 0:
        full_configs = configs_from_ranking(ranking, int(args.full_top_n))
        full_dir = osp.join(args.out_root, "full_top")
        print(f"Rerunning top {len(full_configs)} configs with surface metrics")
        full_rows, full_skipped = run_configs(
            args,
            full_configs,
            full_dir,
            skip_surface_metrics=False,
            write_predictions=bool(args.write_top_predictions),
        )
        write_outputs(full_dir, full_rows, full_skipped, args)


if __name__ == "__main__":
    main()
