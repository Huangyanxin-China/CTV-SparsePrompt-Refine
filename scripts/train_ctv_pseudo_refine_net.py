#!/usr/bin/env python3
"""Train a supervised CTV pseudo-label refinement network.

This is not a "pseudo label as ground truth" experiment. The pseudo label,
SDF core/envelope, sparse prompt, support map, and OAR context are input
features. The target remains the complete local expert CTV mask supplied by
the user.

At inference, the network predicts inclusion probability inside the SDF
envelope. The final mask is constrained as:

    Y_final = prompt U {prob >= threshold} intersect envelope

The threshold is selected on an internal validation split only. Test labels are
used only for final metrics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import SimpleITK as sitk
import torch
import torch.nn.functional as F
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from models.sdf_refine_net import SDFRefineNet
from utils.io import assert_same_geometry
from utils.rules import extract_threshold_rule, threshold_condition
import run_sparse_prompt_core_envelope_workflow as wf
import run_k7_preprocess_variant_screen as screen
from run_traditional_linear_mask_interpolation_baseline import linear_mask_interpolation


DEFAULT_OUT = ROOT / "results/ctv_pseudo_refine_net_k7_supervised"


@dataclass(frozen=True)
class CasePaths:
    case_id: str
    split: str
    ct_path: Path
    label_path: Path
    oar_path: Path


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def read_array(path: Path) -> tuple[np.ndarray, sitk.Image]:
    image = sitk.ReadImage(str(path))
    return sitk.GetArrayFromImage(image), image


def write_mask_like(mask: np.ndarray, ref: sitk.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = sitk.GetImageFromArray(mask.astype(np.uint8))
    out.CopyInformation(ref)
    sitk.WriteImage(out, str(path), useCompression=True)


def dice_score(pred: np.ndarray, gt: np.ndarray) -> float:
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    denom = int(pred.sum()) + int(gt.sum())
    if denom == 0:
        return 1.0
    return float(2.0 * np.logical_and(pred, gt).sum() / denom)


def list_cases(source: Path, oar_source: Path, split: str) -> list[CasePaths]:
    image_dir = source / f"images{split}"
    label_dir = source / f"labels{split}"
    oar_dir = oar_source / f"labels{split}"
    if not image_dir.is_dir() or not label_dir.is_dir() or not oar_dir.is_dir():
        raise FileNotFoundError(f"Missing images/labels/OAR directories for split {split}")

    cases = []
    for ct_path in sorted(image_dir.glob("*_0000.nii.gz")):
        case_id = ct_path.name.replace("_0000.nii.gz", "")
        label_path = label_dir / f"{case_id}.nii.gz"
        oar_path = oar_dir / f"{case_id}.nii.gz"
        if not label_path.exists():
            raise FileNotFoundError(f"Missing CTV label for {case_id}: {label_path}")
        if not oar_path.exists():
            raise FileNotFoundError(f"Missing OAR label for {case_id}: {oar_path}")
        cases.append(CasePaths(case_id, split, ct_path, label_path, oar_path))
    if not cases:
        raise RuntimeError(f"No cases found in {image_dir}")
    return cases


def ctv_voxel_count(path: Path, target_label: int) -> int:
    arr = sitk.GetArrayFromImage(sitk.ReadImage(str(path)))
    return int((arr == int(target_label)).sum())


def filter_nonempty_cases(
    cases: list[CasePaths],
    role: str,
    skipped: list[dict],
    target_label: int,
) -> list[CasePaths]:
    kept = []
    for case in cases:
        n = ctv_voxel_count(case.label_path, target_label)
        if n <= 0:
            skipped.append(
                {
                    "case": case.case_id,
                    "split": case.split,
                    "role": role,
                    "reason": "empty_ctv_no_sparse_prompt",
                    "label_path": str(case.label_path),
                }
            )
            continue
        kept.append(case)
    return kept


def subject_id_from_case(case_id: str, separator: str = "_CT") -> str:
    """Map scan-level case identifiers to a patient/subject grouping key."""
    if separator and separator in case_id:
        return case_id.split(separator, 1)[0]
    return case_id


def make_train_val_split(
    cases: list[CasePaths],
    val_fraction: float,
    seed: int,
    subject_separator: str = "_CT",
) -> tuple[list[CasePaths], list[CasePaths]]:
    """Split complete subject groups so one subject cannot cross train/validation."""
    groups: dict[str, list[CasePaths]] = {}
    for case in cases:
        groups.setdefault(
            subject_id_from_case(case.case_id, subject_separator), []
        ).append(case)
    subject_ids = sorted(groups)
    if len(subject_ids) < 2:
        raise ValueError(
            "At least two distinct subject groups are required for a train/validation split."
        )

    rng = random.Random(int(seed))
    rng.shuffle(subject_ids)
    n_val = max(1, int(round(len(subject_ids) * float(val_fraction))))
    n_val = min(n_val, len(subject_ids) - 1)
    val_subjects = set(subject_ids[:n_val])
    val = sorted(
        [case for subject in val_subjects for case in groups[subject]],
        key=lambda item: item.case_id,
    )
    train = sorted(
        [
            case
            for subject in subject_ids[n_val:]
            for case in groups[subject]
        ],
        key=lambda item: item.case_id,
    )
    return train, val

def load_rule(path: Path) -> dict:
    if not path.exists():
        if path.name != "__embedded_k7_rule__.json":
            raise FileNotFoundError(f"Rule file not found: {path}")
        log("Using embedded K=7 threshold rule.")
        return {
            "type": "threshold",
            "feature": "core_base_vol_ratio",
            "op": "lt",
            "threshold": 0.990869732950405,
            "method_if_true": "linear_core_intersection",
            "method_if_false": "support_100",
        }
    payload = json.loads(path.read_text())
    try:
        return extract_threshold_rule(payload)
    except ValueError as exc:
        raise ValueError(f"Invalid threshold rule in {path}: {exc}") from exc


def file_signature(path: Path) -> dict:
    """Return a cheap cache-invalidation signature for a local input file."""
    if not path.exists():
        return {"missing": True}
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}

def fast_margin_envelope(
    seed: np.ndarray,
    prompt: np.ndarray,
    spinal: np.ndarray,
    spacing_xyz: tuple[float, float, float],
    margin_mm: float,
) -> np.ndarray:
    """Fast high-recall search envelope from inference-available masks.

    The seed is typically pseudo U linear U current-SDF-envelope. The distance
    transform is computed only on a padded seed bbox, avoiding repeated full
    volume SDF candidate generation.
    """
    seed = (seed.astype(bool) | prompt.astype(bool))
    out = np.zeros(seed.shape, dtype=bool)
    if not seed.any():
        out[prompt.astype(bool)] = True
        return out

    spacing_x, spacing_y, spacing_z = [float(v) for v in spacing_xyz]
    spacing_zyx = (spacing_z, spacing_y, spacing_x)
    margin = float(margin_mm)
    pad = np.ceil(margin / np.maximum(np.asarray(spacing_zyx, dtype=float), 1e-6)).astype(int) + 2
    pts = np.argwhere(seed)
    lo = np.maximum(pts.min(axis=0) - pad, 0)
    hi = np.minimum(pts.max(axis=0) + pad + 1, np.asarray(seed.shape))
    slc = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))

    local_seed = seed[slc]
    local_distance = ndimage.distance_transform_edt(~local_seed, sampling=spacing_zyx)
    local_envelope = local_distance <= margin
    out[slc] = local_envelope
    out[spinal.astype(bool)] = False
    out[prompt.astype(bool)] = True
    return out


def anatomy_roi_from_oar(
    oar: np.ndarray,
    prompt: np.ndarray,
    pseudo: np.ndarray,
    spacing_xyz: tuple[float, float, float],
    margin_mm: float,
) -> np.ndarray:
    """Thoracic anatomy ROI from inference-available OAR masks.

    This approximates the earlier organ-ROI step: use segmented organs as an
    anatomical anchor, dilate them physically, and always keep the sparse prompt
    and pseudo label inside the ROI so the refinement step remains well-defined
    when OAR coverage is sparse.
    """
    prompt = prompt.astype(bool)
    pseudo = pseudo.astype(bool)
    local_anchor = prompt | pseudo
    if not local_anchor.any():
        return prompt | pseudo
    spacing_x, spacing_y, spacing_z = [float(v) for v in spacing_xyz]
    spacing_zyx = (spacing_z, spacing_y, spacing_x)
    margin = float(margin_mm)
    pad = np.ceil(margin / np.maximum(np.asarray(spacing_zyx, dtype=float), 1e-6)).astype(int) + 2
    pts = np.argwhere(local_anchor)
    lo = np.maximum(pts.min(axis=0) - pad, 0)
    hi = np.minimum(pts.max(axis=0) + pad + 1, np.asarray(local_anchor.shape))
    slc = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))
    local_seed = (oar[slc] > 0) | prompt[slc] | pseudo[slc]
    local_distance = ndimage.distance_transform_edt(~local_seed, sampling=spacing_zyx)
    out = np.zeros(local_anchor.shape, dtype=bool)
    out[slc] = local_distance <= margin
    out[prompt | pseudo] = True
    return out


def build_pseudo_features(
    ct: np.ndarray,
    gt: np.ndarray,
    gt_img: sitk.Image,
    oar: np.ndarray,
    case_id: str,
    k: int,
    strategy: str,
    pseudo_profile: str,
    refine_profile: str,
    refine_mode: str,
    refine_margin_mm: float,
    anatomy_margin_mm: float,
    rule: dict,
    spinal_label: int = 3,
    precomputed_pseudo: np.ndarray | None = None,
) -> dict[str, np.ndarray | float | str | list[int]]:
    gt = gt.astype(bool)
    selected_z = wf.select_sparse_slices(gt, int(k), strategy, case_id)
    if selected_z.size == 0:
        raise RuntimeError(f"{case_id}: empty CTV, cannot simulate sparse prompt")
    prompt = wf.make_prompt(gt, selected_z)

    if precomputed_pseudo is not None:
        if precomputed_pseudo.shape != gt.shape:
            raise RuntimeError(f"{case_id}: precomputed pseudo shape mismatch {precomputed_pseudo.shape} vs {gt.shape}")
        pseudo = precomputed_pseudo.astype(bool)
        pseudo[prompt] = True
        pseudo_core = pseudo.copy()
        current_envelope = pseudo.copy()
        pseudo_support = pseudo.astype(np.float32)
        linear = pseudo
        feature = float("nan")
        method_name = "precomputed_best_pseudo"
        n_pseudo_candidates = 0
    else:
        linear = linear_mask_interpolation(prompt).astype(bool)
        linear[prompt] = True

        pseudo_methods, pseudo_support, n_pseudo_candidates = wf.build_methods(
            prompt,
            selected_z,
            gt_img.GetSpacing(),
            oar,
            pseudo_profile,
            spinal_label=spinal_label,
        )
        pseudo_core = pseudo_methods["core_only"].astype(bool)
        sdf_base = pseudo_methods["sdf_base"].astype(bool)
        current_envelope = pseudo_methods["envelope"].astype(bool)

        support_masks = {
            f"support_{int(t * 100):03d}": screen.support_mask(pseudo_support, t, prompt).astype(bool)
            for t in (1.0, 0.8, 0.6, 0.4, 0.2)
        }
        linear_core_union = linear | pseudo_core
        linear_core_union[prompt] = True
        linear_core_intersection = linear & pseudo_core
        linear_core_intersection[prompt] = True
        vote2_linear_core_base = (
            linear.astype(np.uint8) + pseudo_core.astype(np.uint8) + sdf_base.astype(np.uint8)
        ) >= 2
        vote2_linear_core_base[prompt] = True
        vote2_linear_core_envelope = (
            linear.astype(np.uint8) + pseudo_core.astype(np.uint8) + current_envelope.astype(np.uint8)
        ) >= 2
        vote2_linear_core_envelope[prompt] = True

        candidate_methods = {
            "linear": linear,
            "sdf_base": sdf_base,
            "sdf_core": pseudo_core,
            "core_only": pseudo_core,
            "envelope": current_envelope,
            "linear_core_union": linear_core_union,
            "linear_core_intersection": linear_core_intersection,
            "vote2_linear_core_base": vote2_linear_core_base,
            "vote2_linear_core_envelope": vote2_linear_core_envelope,
            "support_volume_match_linear": screen.volume_match_support(
                support_masks, int(linear.sum())
            ),
            "support_volume_match_mean_linear_core": screen.volume_match_support(
                support_masks, int((int(linear.sum()) + int(pseudo_core.sum())) / 2)
            ),
            **support_masks,
            **{name: value for name, value in pseudo_methods.items() if value is not None},
        }

        selected_z_array = np.asarray(selected_z, dtype=int)
        shape_features = screen.prompt_shape_features(gt, selected_z_array)
        feature_values = {
            "core_linear_vol_ratio": float(pseudo_core.sum() / max(int(linear.sum()), 1)),
            "base_linear_vol_ratio": float(sdf_base.sum() / max(int(linear.sum()), 1)),
            "core_base_vol_ratio": float(pseudo_core.sum() / max(int(sdf_base.sum()), 1)),
            "core_linear_agreement": wf.dice_score(pseudo_core, linear),
            "base_linear_agreement": wf.dice_score(sdf_base, linear),
            "z_extent": int(selected_z_array[-1] - selected_z_array[0]),
            "z_gap_mean": float(np.diff(selected_z_array).mean()) if selected_z_array.size > 1 else 0.0,
            **shape_features,
        }
        feature_name = str(rule["feature"])
        if feature_name not in feature_values:
            raise ValueError(
                f"Unsupported pseudo-rule feature {feature_name!r}; "
                f"available features: {sorted(feature_values)}"
            )
        feature = float(feature_values[feature_name])
        use_true = threshold_condition(feature, str(rule["op"]), float(rule["threshold"]))
        method_name = str(rule["method_if_true"] if use_true else rule["method_if_false"])
        if method_name not in candidate_methods:
            raise ValueError(
                f"Unsupported pseudo method from rule: {method_name!r}; "
                f"available methods: {sorted(candidate_methods)}"
            )
        pseudo = candidate_methods[method_name].astype(bool, copy=True)
        pseudo[prompt] = True

    spinal = oar == int(spinal_label)
    anatomy_roi = anatomy_roi_from_oar(
        oar,
        prompt,
        pseudo,
        gt_img.GetSpacing(),
        margin_mm=float(anatomy_margin_mm),
    )
    if refine_mode == "profile":
        refine_methods, refine_support, n_refine_candidates = wf.build_methods(
            prompt,
            selected_z,
            gt_img.GetSpacing(),
            oar,
            refine_profile,
            spinal_label=spinal_label,
        )
        core = refine_methods["core_only"].astype(bool)
        envelope = refine_methods["envelope"].astype(bool)
    elif refine_mode == "fast_margin":
        core = pseudo_core.copy()
        refine_support = pseudo_support.astype(np.float32)
        envelope_seed = pseudo | linear | current_envelope
        envelope = fast_margin_envelope(
            envelope_seed,
            prompt,
            spinal,
            gt_img.GetSpacing(),
            margin_mm=float(refine_margin_mm),
        )
        n_refine_candidates = 1
    else:
        raise ValueError(f"Unknown refine_mode: {refine_mode}")
    envelope &= anatomy_roi
    envelope[prompt] = True
    envelope[pseudo] = True
    core &= envelope
    core[prompt] = True
    pseudo &= envelope
    pseudo[prompt] = True

    z_mm = np.arange(gt.shape[0], dtype=np.float32)[:, None]
    prompt_z = np.asarray(selected_z, dtype=np.float32)[None, :]
    nearest_mm = np.min(np.abs(z_mm - prompt_z), axis=1).astype(np.float32) * float(gt_img.GetSpacing()[2])
    z_distance = np.clip(nearest_mm / 60.0, 0.0, 1.0)[:, None, None]
    z_distance = np.broadcast_to(z_distance, gt.shape).astype(np.float32)

    ct_norm = np.clip(ct.astype(np.float32), -1000.0, 1000.0)
    ct_norm = (ct_norm + 1000.0) / 1000.0 - 1.0

    return {
        "ct_norm": ct_norm,
        "pseudo": pseudo.astype(np.float32),
        "core": core.astype(np.float32),
        "envelope": envelope.astype(np.float32),
        "prompt": prompt.astype(np.float32),
        "support": refine_support.astype(np.float32),
        "spinal": spinal.astype(np.float32),
        "anatomy_roi": anatomy_roi.astype(np.float32),
        "z_distance": z_distance,
        "target": gt.astype(np.uint8),
        "selected_z": [int(z) for z in selected_z],
        "pseudo_method": method_name,
        "rule_feature": feature,
        "n_pseudo_candidates": int(n_pseudo_candidates),
        "n_refine_candidates": int(n_refine_candidates),
        "refine_mode": str(refine_mode),
        "refine_margin_mm": float(refine_margin_mm),
        "anatomy_margin_mm": float(anatomy_margin_mm),
    }


def bbox_from_mask(mask: np.ndarray, pad_zyx: tuple[int, int, int], min_size_zyx: tuple[int, int, int]) -> tuple[slice, slice, slice]:
    shape = np.asarray(mask.shape, dtype=int)
    if mask.any():
        pts = np.argwhere(mask)
        lo = pts.min(axis=0)
        hi = pts.max(axis=0) + 1
    else:
        lo = np.zeros(3, dtype=int)
        hi = shape.copy()
    lo = np.maximum(lo - np.asarray(pad_zyx, dtype=int), 0)
    hi = np.minimum(hi + np.asarray(pad_zyx, dtype=int), shape)

    min_size = np.asarray(min_size_zyx, dtype=int)
    for axis in range(3):
        length = int(hi[axis] - lo[axis])
        target = max(length, int(min_size[axis]))
        target = int(math.ceil(target / 8.0) * 8)
        extra = target - length
        left = extra // 2
        right = extra - left
        lo[axis] = max(int(lo[axis]) - left, 0)
        hi[axis] = min(int(hi[axis]) + right, int(shape[axis]))
        length = int(hi[axis] - lo[axis])
        if length < target:
            deficit = target - length
            lo[axis] = max(int(lo[axis]) - deficit, 0)
            hi[axis] = min(int(lo[axis]) + target, int(shape[axis]))
        if int(hi[axis] - lo[axis]) % 8 != 0 and int(hi[axis] - lo[axis]) < int(shape[axis]):
            hi[axis] = min(int(shape[axis]), int(hi[axis]) + (8 - int(hi[axis] - lo[axis]) % 8))
    return tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))


def crop_array(arr: np.ndarray, slices: tuple[slice, slice, slice]) -> np.ndarray:
    return arr[slices]


def pad_to_size(arr: np.ndarray, target_shape: tuple[int, int, int], value: float = 0.0) -> np.ndarray:
    pads = []
    for got, want in zip(arr.shape[-3:], target_shape):
        if got > want:
            raise ValueError(f"Cannot pad shape {arr.shape[-3:]} down to {target_shape}")
        extra = int(want) - int(got)
        pads.append((0, extra))
    if arr.ndim == 4:
        pad_width = [(0, 0), *pads]
    else:
        pad_width = pads
    return np.pad(arr, pad_width, mode="constant", constant_values=value)


def crop_or_pad_patch(arr: np.ndarray, start: np.ndarray, patch_size: tuple[int, int, int], value: float = 0.0) -> np.ndarray:
    shape = np.asarray(arr.shape[-3:], dtype=int)
    start = np.asarray(start, dtype=int)
    end = start + np.asarray(patch_size, dtype=int)
    src_lo = np.maximum(start, 0)
    src_hi = np.minimum(end, shape)
    dst_lo = src_lo - start
    dst_hi = dst_lo + (src_hi - src_lo)
    if arr.ndim == 4:
        out = np.full((arr.shape[0], *patch_size), value, dtype=arr.dtype)
        out[:, dst_lo[0]:dst_hi[0], dst_lo[1]:dst_hi[1], dst_lo[2]:dst_hi[2]] = arr[
            :, src_lo[0]:src_hi[0], src_lo[1]:src_hi[1], src_lo[2]:src_hi[2]
        ]
    else:
        out = np.full(patch_size, value, dtype=arr.dtype)
        out[dst_lo[0]:dst_hi[0], dst_lo[1]:dst_hi[1], dst_lo[2]:dst_hi[2]] = arr[
            src_lo[0]:src_hi[0], src_lo[1]:src_hi[1], src_lo[2]:src_hi[2]
        ]
    return out


def prepare_case_cache(
    case: CasePaths,
    cache_dir: Path,
    feature_source: str,
    precomputed_pseudo_path: Path | None,
    k: int,
    strategy: str,
    pseudo_profile: str,
    refine_profile: str,
    refine_mode: str,
    refine_margin_mm: float,
    anatomy_margin_mm: float,
    rule: dict,
    target_label: int,
    spinal_label: int,
    roi_pad_zyx: tuple[int, int, int],
    min_roi_zyx: tuple[int, int, int],
    force: bool = False,
) -> dict:
    out_path = cache_dir / case.split / f"{case.case_id}.npz"
    meta_path = cache_dir / case.split / f"{case.case_id}.json"
    rule_signature = hashlib.sha256(
        json.dumps(rule, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    input_paths = [case.ct_path, case.label_path, case.oar_path]
    if precomputed_pseudo_path is not None:
        input_paths.append(precomputed_pseudo_path)
    input_signatures = {str(path): file_signature(path) for path in input_paths}
    inputs_available = all(not signature.get("missing") for signature in input_signatures.values())
    if out_path.exists() and meta_path.exists() and not force and inputs_available:
        cached = json.loads(meta_path.read_text())
        if (
            int(cached.get("k", -1)) == int(k)
            and str(cached.get("strategy", "")) == str(strategy)
            and str(cached.get("feature_source", "")) == str(feature_source)
            and str(cached.get("pseudo_profile", "")) == str(pseudo_profile)
            and str(cached.get("refine_profile", "")) == str(refine_profile)
            and str(cached.get("refine_mode", "")) == str(refine_mode)
            and abs(float(cached.get("refine_margin_mm", -1.0)) - float(refine_margin_mm)) < 1e-8
            and abs(float(cached.get("anatomy_margin_mm", -1.0)) - float(anatomy_margin_mm)) < 1e-8
            and cached.get("rule_signature") == rule_signature
            and int(cached.get("target_label", -1)) == int(target_label)
            and int(cached.get("spinal_label", -1)) == int(spinal_label)
            and cached.get("roi_pad_zyx") == [int(v) for v in roi_pad_zyx]
            and cached.get("min_roi_zyx") == [int(v) for v in min_roi_zyx]
            and cached.get("input_signatures") == input_signatures
        ):
            return cached
        log(f"cache stale for {case.case_id}; rebuilding")

    ct, ct_img = read_array(case.ct_path)
    gt_arr, gt_img = read_array(case.label_path)
    oar, oar_img = read_array(case.oar_path)
    if ct.shape != gt_arr.shape or gt_arr.shape != oar.shape:
        raise RuntimeError(f"{case.case_id}: shape mismatch CT={ct.shape}, CTV={gt_arr.shape}, OAR={oar.shape}")
    try:
        assert_same_geometry(gt_img, ct_img, "CTV", "CT")
        assert_same_geometry(gt_img, oar_img, "CTV", "OAR")
    except ValueError as exc:
        raise RuntimeError(f"{case.case_id}: {exc}") from exc

    gt = gt_arr == int(target_label)
    precomputed_pseudo = None
    if feature_source == "precomputed":
        if precomputed_pseudo_path is None:
            raise RuntimeError(f"{case.case_id}: feature_source=precomputed but no pseudo path was provided")
        if not precomputed_pseudo_path.exists():
            raise FileNotFoundError(f"{case.case_id}: missing precomputed pseudo label: {precomputed_pseudo_path}")
        precomputed_arr, precomputed_img = read_array(precomputed_pseudo_path)
        if precomputed_arr.shape != gt.shape:
            raise RuntimeError(
                f"{case.case_id}: precomputed pseudo shape mismatch {precomputed_arr.shape} vs {gt.shape}"
            )
        try:
            assert_same_geometry(gt_img, precomputed_img, "CTV", "precomputed pseudo")
        except ValueError as exc:
            raise RuntimeError(f"{case.case_id}: {exc}") from exc
        precomputed_pseudo = precomputed_arr > 0
    elif feature_source != "generate":
        raise ValueError(f"Unknown feature_source: {feature_source}")

    features = build_pseudo_features(
        ct,
        gt,
        gt_img,
        oar,
        case.case_id,
        k,
        strategy,
        pseudo_profile,
        refine_profile,
        refine_mode,
        refine_margin_mm,
        anatomy_margin_mm,
        rule,
        spinal_label=spinal_label,
        precomputed_pseudo=precomputed_pseudo,
    )
    envelope = features["envelope"].astype(bool)
    prompt = features["prompt"].astype(bool)
    pseudo = features["pseudo"].astype(bool)
    anatomy_roi = features["anatomy_roi"].astype(bool)
    crop_mask = envelope | prompt | pseudo | anatomy_roi
    slices = bbox_from_mask(crop_mask, roi_pad_zyx, min_roi_zyx)

    x = np.stack(
        [
            crop_array(features["ct_norm"], slices),
            crop_array(features["pseudo"], slices),
            crop_array(features["core"], slices),
            crop_array(features["envelope"], slices),
            crop_array(features["prompt"], slices),
            crop_array(features["support"], slices),
            crop_array(features["spinal"], slices),
            crop_array(features["anatomy_roi"], slices),
            crop_array(features["z_distance"], slices),
        ],
        axis=0,
    ).astype(np.float16)
    y = crop_array(features["target"], slices).astype(np.uint8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        x=x,
        y=y,
        crop_start=np.asarray([s.start for s in slices], dtype=np.int32),
        crop_stop=np.asarray([s.stop for s in slices], dtype=np.int32),
        full_shape=np.asarray(gt.shape, dtype=np.int32),
        selected_z=np.asarray(features["selected_z"], dtype=np.int32),
    )
    meta = {
        "case": case.case_id,
        "split": case.split,
        "cache_path": str(out_path),
        "ct_path": str(case.ct_path),
        "label_path": str(case.label_path),
        "oar_path": str(case.oar_path),
        "shape_zyx": [int(v) for v in gt.shape],
        "spacing_xyz": [float(v) for v in gt_img.GetSpacing()],
        "k": int(k),
        "strategy": str(strategy),
        "feature_source": str(feature_source),
        "precomputed_pseudo_path": str(precomputed_pseudo_path) if precomputed_pseudo_path is not None else "",
        "rule_threshold": float(rule["threshold"]),
        "rule_signature": rule_signature,
        "rule": dict(rule),
        "target_label": int(target_label),
        "spinal_label": int(spinal_label),
        "input_signatures": input_signatures,
        "roi_pad_zyx": [int(v) for v in roi_pad_zyx],
        "min_roi_zyx": [int(v) for v in min_roi_zyx],
        "crop_start_zyx": [int(s.start) for s in slices],
        "crop_stop_zyx": [int(s.stop) for s in slices],
        "crop_shape_zyx": [int(s.stop - s.start) for s in slices],
        "selected_z": features["selected_z"],
        "pseudo_method": str(features["pseudo_method"]),
        "rule_feature": float(features["rule_feature"]),
        "pseudo_profile": str(pseudo_profile),
        "refine_profile": str(refine_profile),
        "refine_mode": str(refine_mode),
        "refine_margin_mm": float(refine_margin_mm),
        "anatomy_margin_mm": float(anatomy_margin_mm),
        "n_pseudo_candidates": int(features["n_pseudo_candidates"]),
        "n_refine_candidates": int(features["n_refine_candidates"]),
        "gt_voxels": int(gt.sum()),
        "pseudo_voxels": int(pseudo.sum()),
        "core_voxels": int(np.asarray(features["core"]).astype(bool).sum()),
        "envelope_voxels": int(envelope.sum()),
        "prompt_voxels": int(prompt.sum()),
        "pseudo_dice": dice_score(pseudo, gt),
        "envelope_recall": float(np.logical_and(envelope, gt).sum() / max(int(gt.sum()), 1)),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def write_manifest(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def serializable_args(args: argparse.Namespace) -> dict:
    return {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as data:
        return {key: data[key] for key in data.files}


def sample_patch(data: dict[str, np.ndarray], patch_size: tuple[int, int, int], rng: np.random.Generator) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    x = data["x"].astype(np.float32, copy=False)
    y = data["y"].astype(np.float32, copy=False)
    envelope = x[3] > 0.5
    prompt = x[4] > 0.5
    candidate = (y > 0.5) | envelope | prompt
    pts = np.argwhere(candidate)
    if pts.size == 0:
        center = np.asarray(y.shape) // 2
    else:
        center = pts[int(rng.integers(0, len(pts)))]
    jitter = np.asarray([rng.integers(-max(s // 8, 1), max(s // 8, 1) + 1) for s in patch_size], dtype=int)
    center = center + jitter
    start = center - (np.asarray(patch_size, dtype=int) // 2)

    xp = crop_or_pad_patch(x, start, patch_size, value=0.0)
    yp = crop_or_pad_patch(y, start, patch_size, value=0.0)
    envp = xp[3] > 0.5
    lossp = (envp | (yp > 0.5) | (xp[4] > 0.5)).astype(np.float32)
    return (
        torch.from_numpy(xp[None]).float(),
        torch.from_numpy(yp[None, None]).float(),
        torch.from_numpy(lossp[None, None]).float(),
    )


def dice_loss_from_logits(logits: torch.Tensor, target: torch.Tensor, mask: torch.Tensor, eps: float = 1e-5) -> torch.Tensor:
    prob = torch.sigmoid(logits) * mask
    target = target * mask
    inter = torch.sum(prob * target)
    denom = torch.sum(prob) + torch.sum(target)
    return 1.0 - (2.0 * inter + eps) / (denom + eps)


def masked_bce_with_logits(logits: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    selected = mask > 0.5
    if not torch.any(selected):
        return F.binary_cross_entropy_with_logits(logits, target)
    logits_s = logits[selected]
    target_s = target[selected]
    pos = torch.sum(target_s)
    neg = torch.sum(1.0 - target_s)
    pos_weight = torch.clamp(neg / torch.clamp(pos, min=1.0), min=1.0, max=20.0)
    return F.binary_cross_entropy_with_logits(logits_s, target_s, pos_weight=pos_weight)


@torch.no_grad()
def predict_case(model: torch.nn.Module, data: dict[str, np.ndarray], device: torch.device) -> np.ndarray:
    x = torch.from_numpy(data["x"].astype(np.float32, copy=False)[None]).to(device)
    model.eval()
    logits = model(x)
    prob = torch.sigmoid(logits)[0, 0].detach().cpu().numpy().astype(np.float32)
    return prob


def evaluate_cases(
    model: torch.nn.Module,
    rows: list[dict],
    device: torch.device,
    thresholds: list[float],
    selected_threshold: float | None = None,
    output_dir: Path | None = None,
    source_cases: dict[str, CasePaths] | None = None,
) -> tuple[list[dict], dict]:
    eval_rows = []
    by_threshold = {float(t): [] for t in thresholds}
    for row in rows:
        data = load_npz(Path(row["cache_path"]))
        prob = predict_case(model, data, device)
        y = data["y"].astype(bool)
        x = data["x"].astype(np.float32, copy=False)
        envelope = x[3] > 0.5
        prompt = x[4] > 0.5
        pseudo = x[1] > 0.5
        pseudo_dice = dice_score(pseudo, y)
        case_id = row["case"]
        for thr in thresholds:
            pred = ((prob >= float(thr)) & envelope) | prompt
            d = dice_score(pred, y)
            by_threshold[float(thr)].append(d)
            if selected_threshold is not None and abs(float(thr) - float(selected_threshold)) < 1e-8:
                eval_rows.append(
                    {
                        "case": case_id,
                        "split": row["split"],
                        "threshold": float(thr),
                        "pseudo_dice": pseudo_dice,
                        "refine_dice": d,
                        "delta_dice": d - pseudo_dice,
                        "pseudo_voxels": int(pseudo.sum()),
                        "refine_voxels": int(pred.sum()),
                        "gt_voxels": int(y.sum()),
                    }
                )
                if output_dir is not None and source_cases is not None:
                    full = np.zeros(tuple(int(v) for v in data["full_shape"]), dtype=np.uint8)
                    start = data["crop_start"].astype(int)
                    stop = data["crop_stop"].astype(int)
                    slc = tuple(slice(int(a), int(b)) for a, b in zip(start, stop))
                    full[slc] = pred.astype(np.uint8)
                    case = source_cases[case_id]
                    _, ref = read_array(case.label_path)
                    write_mask_like(full, ref, output_dir / f"{case_id}.nii.gz")
    summary = {}
    for thr, values in by_threshold.items():
        arr = np.asarray(values, dtype=float)
        summary[str(thr)] = {
            "mean_dice": float(arr.mean()) if arr.size else float("nan"),
            "std_dice": float(arr.std()) if arr.size else float("nan"),
            "n": int(arr.size),
        }
    return eval_rows, summary


def train_model(args: argparse.Namespace, train_rows: list[dict], val_rows: list[dict], out_dir: Path) -> tuple[Path, float, dict]:
    rng = np.random.default_rng(int(args.seed))
    random.seed(int(args.seed))
    torch.manual_seed(int(args.seed))
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    log(f"Training device: {device}")

    train_data = [load_npz(Path(row["cache_path"])) for row in train_rows]
    model = SDFRefineNet(in_channels=9, out_channels=1, base_filters=int(args.base_filters)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(args.lr), weight_decay=float(args.weight_decay))
    scaler = torch.amp.GradScaler("cuda", enabled=bool(args.amp and device.type == "cuda"))

    patch_size = tuple(int(v) for v in args.patch_size)
    thresholds = [round(float(v), 2) for v in np.arange(float(args.threshold_min), float(args.threshold_max) + 1e-6, float(args.threshold_step))]
    best = {"val_refine_mean": -1.0, "epoch": -1, "threshold": 0.5, "val_pseudo_mean": None}
    best_path = out_dir / "checkpoints/checkpoint_best.pt"
    latest_path = out_dir / "checkpoints/checkpoint_latest.pt"
    best_path.parent.mkdir(parents=True, exist_ok=True)
    history = []

    for epoch in range(1, int(args.max_epochs) + 1):
        model.train()
        losses = []
        for _ in range(int(args.steps_per_epoch)):
            data = train_data[int(rng.integers(0, len(train_data)))]
            x, y, mask = sample_patch(data, patch_size, rng)
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            mask = mask.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=bool(args.amp and device.type == "cuda")):
                logits = model(x)
                bce = masked_bce_with_logits(logits, y, mask)
                dice = dice_loss_from_logits(logits, y, mask)
                loss = bce + float(args.dice_loss_weight) * dice
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))

        row = {"epoch": epoch, "loss": float(np.mean(losses))}
        if epoch % int(args.val_interval) == 0 or epoch == 1 or epoch == int(args.max_epochs):
            _, val_summary = evaluate_cases(model, val_rows, device, thresholds)
            val_pseudo = np.asarray([float(r["pseudo_dice"]) for r in val_rows], dtype=float)
            best_thr, best_stat = max(val_summary.items(), key=lambda item: item[1]["mean_dice"])
            row.update(
                {
                    "val_best_threshold": float(best_thr),
                    "val_refine_mean": float(best_stat["mean_dice"]),
                    "val_pseudo_mean": float(val_pseudo.mean()),
                    "val_delta_mean": float(best_stat["mean_dice"] - val_pseudo.mean()),
                }
            )
            log(
                f"epoch={epoch:04d} loss={row['loss']:.4f} "
                f"val_refine={row['val_refine_mean']:.4f} "
                f"val_pseudo={row['val_pseudo_mean']:.4f} "
                f"thr={row['val_best_threshold']:.2f}"
            )
            if float(best_stat["mean_dice"]) > float(best["val_refine_mean"]):
                best = {
                    "val_refine_mean": float(best_stat["mean_dice"]),
                    "epoch": int(epoch),
                    "threshold": float(best_thr),
                    "val_pseudo_mean": float(val_pseudo.mean()),
                }
                torch.save(
                    {
                        "model": model.state_dict(),
                        "args": serializable_args(args),
                        "best": best,
                        "history": history,
                    },
                    best_path,
                )
        else:
            log(f"epoch={epoch:04d} loss={row['loss']:.4f}")
        history.append(row)
        torch.save(
            {
                "model": model.state_dict(),
                "args": serializable_args(args),
                "best": best,
                "history": history,
            },
            latest_path,
        )
        write_manifest(out_dir / "training_history.csv", history)

    return best_path, float(best["threshold"]), best


def parse_zyx(values: list[int], name: str) -> tuple[int, int, int]:
    if len(values) != 3:
        raise argparse.ArgumentTypeError(f"{name} expects exactly 3 integers in z y x order")
    return tuple(int(v) for v in values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Supervised pseudo-to-true CTV refinement network.")
    parser.add_argument("--source", type=Path, required=True, help="Local dataset root containing imagesTr/labelsTr/imagesTs/labelsTs.")
    parser.add_argument("--oar_source", type=Path, required=True, help="Local OAR dataset root containing labelsTr/labelsTs.")
    parser.add_argument("--pseudo_train_dir", type=Path, default=None, help="Required when --feature_source precomputed.")
    parser.add_argument("--pseudo_test_dir", type=Path, default=None, help="Required when --feature_source precomputed.")
    parser.add_argument("--out_dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--rule_json", type=Path, default=None, help="Optional preprocessing-rule JSON; embedded K=7 rule is used when omitted.")
    parser.add_argument("--feature_source", default="precomputed", choices=("precomputed", "generate"))
    parser.add_argument("--k", type=int, default=7)
    parser.add_argument(
        "--target_label",
        type=int,
        default=1,
        help="CTV label value in complete target masks.",
    )
    parser.add_argument(
        "--spinal_label",
        type=int,
        default=3,
        help="OAR label value used for spinal-cord exclusion.",
    )
    parser.add_argument("--strategy", default="even_nonempty")
    parser.add_argument("--pseudo_profile", default="current", choices=sorted(wf.PROFILES.keys()))
    parser.add_argument("--refine_profile", default="high_recall", choices=sorted(wf.PROFILES.keys()))
    parser.add_argument("--refine_mode", default="fast_margin", choices=("fast_margin", "profile"))
    parser.add_argument("--refine_margin_mm", type=float, default=25.0)
    parser.add_argument("--anatomy_margin_mm", type=float, default=40.0)
    parser.add_argument("--seed", type=int, default=20260603)
    parser.add_argument("--val_fraction", type=float, default=0.18)
    parser.add_argument(
        "--subject_separator",
        default="_CT",
        help=(
            "Case-ID separator used to group repeated scans from one subject. "
            "For example, P001_CT1 and P001_CT2 map to P001. Pass an empty string "
            "only when every case is known to be an independent subject."
        ),
    )
    parser.add_argument("--roi_pad", type=int, nargs=3, default=[12, 32, 32], metavar=("Z", "Y", "X"))
    parser.add_argument("--min_roi", type=int, nargs=3, default=[64, 128, 128], metavar=("Z", "Y", "X"))
    parser.add_argument("--patch_size", type=int, nargs=3, default=[64, 128, 128], metavar=("Z", "Y", "X"))
    parser.add_argument("--base_filters", type=int, default=8)
    parser.add_argument("--max_epochs", type=int, default=80)
    parser.add_argument("--steps_per_epoch", type=int, default=48)
    parser.add_argument("--val_interval", type=int, default=5)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--dice_loss_weight", type=float, default=1.0)
    parser.add_argument("--threshold_min", type=float, default=0.20)
    parser.add_argument("--threshold_max", type=float, default=0.80)
    parser.add_argument("--threshold_step", type=float, default=0.05)
    parser.add_argument("--case_limit", type=int, default=0, help="Debug only: limit train/test case counts after deterministic split.")
    parser.add_argument("--force_cache", action="store_true")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--amp", action="store_true")
    args = parser.parse_args()

    args.source = args.source.resolve()
    args.oar_source = args.oar_source.resolve()
    if args.feature_source == "precomputed" and (args.pseudo_train_dir is None or args.pseudo_test_dir is None):
        parser.error("--pseudo_train_dir and --pseudo_test_dir are required when --feature_source precomputed")
    if args.pseudo_train_dir is not None:
        args.pseudo_train_dir = args.pseudo_train_dir.resolve()
    if args.pseudo_test_dir is not None:
        args.pseudo_test_dir = args.pseudo_test_dir.resolve()
    args.out_dir = args.out_dir.resolve()
    if args.rule_json is not None:
        args.rule_json = args.rule_json.resolve()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}, indent=2) + "\n")

    rule = load_rule(args.rule_json) if args.rule_json is not None else load_rule(Path("__embedded_k7_rule__.json"))
    skipped_rows = []
    all_train = filter_nonempty_cases(
        list_cases(args.source, args.oar_source, "Tr"),
        "train_pool",
        skipped_rows,
        args.target_label,
    )
    test_cases = filter_nonempty_cases(
        list_cases(args.source, args.oar_source, "Ts"),
        "test",
        skipped_rows,
        args.target_label,
    )
    train_cases, val_cases = make_train_val_split(
        all_train,
        args.val_fraction,
        args.seed,
        subject_separator=args.subject_separator,
    )
    if args.case_limit > 0:
        train_cases = train_cases[: max(1, args.case_limit)]
        val_cases = val_cases[: max(1, min(args.case_limit, len(val_cases)))]
        test_cases = test_cases[: max(1, args.case_limit)]

    log(f"source={args.source}")
    log(f"oar_source={args.oar_source}")
    log(f"feature_source={args.feature_source}")
    if args.feature_source == "precomputed":
        log(f"pseudo_train_dir={args.pseudo_train_dir}")
        log(f"pseudo_test_dir={args.pseudo_test_dir}")
    log(f"out_dir={out_dir}")
    train_subjects = {
        subject_id_from_case(case.case_id, args.subject_separator)
        for case in train_cases
    }
    val_subjects = {
        subject_id_from_case(case.case_id, args.subject_separator)
        for case in val_cases
    }
    if train_subjects & val_subjects:
        raise RuntimeError(
            f"Subject leakage across train/validation: {sorted(train_subjects & val_subjects)}"
        )
    log(
        f"case split: train={len(train_cases)} ({len(train_subjects)} subjects), "
        f"val={len(val_cases)} ({len(val_subjects)} subjects), test={len(test_cases)}"
    )
    log(f"skipped empty/no-prompt cases={len(skipped_rows)}")
    log("refine target: expert CTV; pseudo/core/envelope/prompt/OAR are input features only")

    cache_dir = out_dir / "cache"
    roi_pad = parse_zyx(args.roi_pad, "roi_pad")
    min_roi = parse_zyx(args.min_roi, "min_roi")
    rows = []

    def cache_roles(role_cases: list[tuple[str, list[CasePaths]]]) -> None:
        cached = {row["case"]: row for row in rows}
        for split_name, cases in role_cases:
            for idx, case in enumerate(cases, start=1):
                if case.case_id in cached and cached[case.case_id].get("role") == split_name:
                    continue
                log(f"cache {split_name} [{idx}/{len(cases)}] {case.case_id}")
                if args.feature_source == "precomputed":
                    pseudo_dir = args.pseudo_train_dir if case.split == "Tr" else args.pseudo_test_dir
                    precomputed_pseudo_path = pseudo_dir / f"{case.case_id}.nii.gz"
                else:
                    precomputed_pseudo_path = None
                try:
                    meta = prepare_case_cache(
                        case,
                        cache_dir,
                        args.feature_source,
                        precomputed_pseudo_path,
                        args.k,
                        args.strategy,
                        args.pseudo_profile,
                        args.refine_profile,
                        args.refine_mode,
                        args.refine_margin_mm,
                        args.anatomy_margin_mm,
                        rule,
                        args.target_label,
                        args.spinal_label,
                        roi_pad,
                        min_roi,
                        force=args.force_cache,
                    )
                except RuntimeError as exc:
                    if "empty CTV" not in str(exc):
                        raise
                    skipped_rows.append(
                        {
                            "case": case.case_id,
                            "split": case.split,
                            "role": split_name,
                            "reason": "empty_ctv_no_sparse_prompt",
                            "label_path": str(case.label_path),
                        }
                    )
                    log(f"skip {case.case_id}: empty CTV, no sparse prompt")
                    continue
                meta["role"] = split_name
                rows.append(meta)
                cached[case.case_id] = meta

    def write_cache_reports() -> dict:
        write_manifest(out_dir / "cache_manifest.csv", rows)
        write_manifest(out_dir / "skipped_cases.csv", skipped_rows)
        summary = {}
        for role in ("train", "val", "test"):
            role_rows = [row for row in rows if row["role"] == role]
            pseudo = np.asarray([float(row["pseudo_dice"]) for row in role_rows], dtype=float)
            recall = np.asarray([float(row["envelope_recall"]) for row in role_rows], dtype=float)
            crop_shapes = np.asarray([row["crop_shape_zyx"] for row in role_rows], dtype=int)
            summary[role] = {
                "n": len(role_rows),
                "pseudo_dice_mean": float(pseudo.mean()) if pseudo.size else None,
                "pseudo_dice_std": float(pseudo.std()) if pseudo.size else None,
                "envelope_recall_mean": float(recall.mean()) if recall.size else None,
                "crop_shape_zyx_max": crop_shapes.max(axis=0).astype(int).tolist() if crop_shapes.size else None,
                "crop_shape_zyx_median": np.median(crop_shapes, axis=0).astype(float).tolist() if crop_shapes.size else None,
            }
        (out_dir / "preflight_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        log("preflight summary: " + json.dumps(summary, ensure_ascii=False))
        return summary

    if args.dry_run:
        cache_roles([("train", train_cases), ("val", val_cases), ("test", test_cases)])
    else:
        cache_roles([("train", train_cases), ("val", val_cases)])
    write_cache_reports()

    if args.dry_run:
        log("dry_run complete; no training launched")
        return

    train_rows = [row for row in rows if row["role"] == "train"]
    val_rows = [row for row in rows if row["role"] == "val"]
    best_path, threshold, best = train_model(args, train_rows, val_rows, out_dir)

    cache_roles([("test", test_cases)])
    write_cache_reports()
    test_rows = [row for row in rows if row["role"] == "test"]

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model = SDFRefineNet(in_channels=9, out_channels=1, base_filters=int(args.base_filters)).to(device)
    ckpt = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    thresholds = [float(threshold)]

    test_case_map = {case.case_id: case for case in test_cases}
    val_eval_rows, _ = evaluate_cases(
        model,
        val_rows,
        device,
        thresholds,
        selected_threshold=threshold,
        output_dir=out_dir / "predictions_val",
        source_cases={case.case_id: case for case in val_cases},
    )
    test_eval_rows, _ = evaluate_cases(
        model,
        test_rows,
        device,
        thresholds,
        selected_threshold=threshold,
        output_dir=out_dir / "predictions_test",
        source_cases=test_case_map,
    )
    write_manifest(out_dir / "val_metrics.csv", val_eval_rows)
    write_manifest(out_dir / "test_metrics.csv", test_eval_rows)

    def summarize_eval(eval_rows: list[dict]) -> dict:
        pseudo = np.asarray([float(r["pseudo_dice"]) for r in eval_rows], dtype=float)
        refine = np.asarray([float(r["refine_dice"]) for r in eval_rows], dtype=float)
        delta = refine - pseudo
        return {
            "n": int(len(eval_rows)),
            "pseudo_mean": float(pseudo.mean()) if pseudo.size else None,
            "refine_mean": float(refine.mean()) if refine.size else None,
            "delta_mean": float(delta.mean()) if delta.size else None,
            "improved": int(np.sum(delta > 1e-8)) if delta.size else 0,
            "worse": int(np.sum(delta < -1e-8)) if delta.size else 0,
        }

    final_summary = {
        "best_checkpoint": str(best_path),
        "selected_threshold": float(threshold),
        "best_validation": best,
        "accepted_by_validation_gate": bool(float(best["val_refine_mean"]) > float(best["val_pseudo_mean"])),
        "val": summarize_eval(val_eval_rows),
        "test": summarize_eval(test_eval_rows),
        "note": "Pseudo labels are inputs; expert CTV masks are the supervised target. Test labels are used only for final metrics.",
    }
    (out_dir / "summary.json").write_text(json.dumps(final_summary, indent=2) + "\n")
    log("final summary: " + json.dumps(final_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
