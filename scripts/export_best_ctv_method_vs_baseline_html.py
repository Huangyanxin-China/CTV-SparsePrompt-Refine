#!/usr/bin/env python3
"""Export per-case CTV comparison, all-slice HTML overlays, and 3D masks.

The deployable best method is the train-calibrated threshold rule selected in
results/data_preprocess_variant_screen_k7_20260602/summary.json. The baseline
is the K=7 linear mask interpolation result, which uses the same sparse prompt
protocol.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import sys
from glob import glob
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from PIL import Image, ImageDraw
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_sparse_prompt_core_envelope_workflow as wf
from run_k7_preprocess_variant_screen import support_mask
from run_traditional_linear_mask_interpolation_baseline import linear_mask_interpolation


CT_DIR = ROOT / "nnunet_runs/raw/Dataset015_CTV_Dataset004Split/imagesTs"
GT_DIR = ROOT / "nnunet_runs/raw/Dataset015_CTV_Dataset004Split/labelsTs"
LINEAR_DIR = ROOT / "results/traditional_linear_mask_interpolation_k7/labels"
VARIANT_DIR = ROOT / "results/data_preprocess_variant_screen_k7_20260602"
VARIANT_METRICS = VARIANT_DIR / "test_metrics_with_surface.csv"
VARIANT_SUMMARY = VARIANT_DIR / "summary.json"
EXISTING_EXPORT_DIR = ROOT / "reports/best_ctv_method_vs_best_baseline_20260603"

COLORS = {
    "gt": (46, 204, 113),
    "baseline": (255, 149, 0),
    "ours": (220, 38, 38),
    "prompt": (30, 144, 255),
}


def case_names(label_dir: Path) -> list[str]:
    return [Path(path).name.replace(".nii.gz", "") for path in sorted(glob(str(label_dir / "*.nii.gz")))]


def read_image(path: Path) -> tuple[np.ndarray, sitk.Image]:
    image = sitk.ReadImage(str(path))
    return sitk.GetArrayFromImage(image), image


def write_like(mask: np.ndarray, ref_image: sitk.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = sitk.GetImageFromArray(mask.astype(np.uint8))
    out.CopyInformation(ref_image)
    sitk.WriteImage(out, str(path))


def read_bool(path: Path) -> np.ndarray:
    return sitk.GetArrayFromImage(sitk.ReadImage(str(path))) > 0


def dice_score(pred: np.ndarray, gt: np.ndarray) -> float:
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    denom = int(pred.sum()) + int(gt.sum())
    if denom == 0:
        return 1.0
    return float(2.0 * np.logical_and(pred, gt).sum() / denom)


def safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "--"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "--"
    if math.isnan(value):
        return "--"
    return f"{value:.{digits}f}"


def prompt_z_mask(prompt: np.ndarray) -> np.ndarray:
    z = np.where(prompt.reshape(prompt.shape[0], -1).any(axis=1))[0]
    mask = np.zeros(prompt.shape[0], dtype=bool)
    mask[z] = True
    return mask


def load_rule() -> dict:
    with VARIANT_SUMMARY.open() as f:
        summary = json.load(f)
    rule = summary["threshold_rule"]
    expected = {
        "type": "threshold",
        "feature": "core_base_vol_ratio",
        "op": "lt",
        "method_if_true": "linear_core_intersection",
        "method_if_false": "support_100",
    }
    for key, value in expected.items():
        if rule.get(key) != value:
            raise RuntimeError(f"Unexpected best-rule field {key}: {rule.get(key)!r}, expected {value!r}")
    return rule


def load_expected_ours_dice() -> dict[str, float]:
    out: dict[str, float] = {}
    with VARIANT_METRICS.open() as f:
        for row in csv.DictReader(f):
            if row.get("method") == "train_calibrated_support_intersection_rule":
                out[row["case"]] = safe_float(row.get("dice"))
    if not out:
        raise RuntimeError(f"No train_calibrated_support_intersection_rule rows found in {VARIANT_METRICS}")
    return out


def load_existing_export_rows() -> dict[str, dict]:
    path = EXISTING_EXPORT_DIR / "per_case_dice_comparison.csv"
    if not path.exists():
        raise RuntimeError(f"Existing export CSV not found: {path}")
    with path.open(newline="") as f:
        rows = {row["case"]: row for row in csv.DictReader(f)}
    if not rows:
        raise RuntimeError(f"No existing export rows found in {path}")
    return rows


def load_existing_masks(case_id: str, existing_rows: dict[str, dict]) -> dict[str, np.ndarray | sitk.Image | list[int]]:
    row = existing_rows.get(case_id)
    if row is None:
        raise RuntimeError(f"No existing export row for {case_id}")

    gt, gt_img = read_image(GT_DIR / f"{case_id}.nii.gz")
    gt = gt > 0
    baseline = read_bool(EXISTING_EXPORT_DIR / "nii/baseline_linear_mask_interpolation_k7" / f"{case_id}.nii.gz")
    ours = read_bool(EXISTING_EXPORT_DIR / "nii/ours_train_calibrated_support_intersection_rule" / f"{case_id}.nii.gz")
    prompt = read_bool(EXISTING_EXPORT_DIR / "nii/sparse_prompt_k7_even_nonempty" / f"{case_id}.nii.gz")
    selected_z = [int(z) for z in row.get("selected_z", "").split(";") if z]
    if not selected_z:
        selected_z = [int(z) for z in np.where(prompt.reshape(prompt.shape[0], -1).any(axis=1))[0]]

    return {
        "gt": gt,
        "gt_img": gt_img,
        "prompt": prompt,
        "baseline": baseline,
        "ours": ours,
        "selected_z": selected_z,
        "chosen_source": row.get("chosen_source", "existing_export"),
        "rule_feature_value": safe_float(row.get("rule_feature_value")),
    }


def build_masks(case_id: str, rule: dict) -> dict[str, np.ndarray | sitk.Image | list[int]]:
    gt, gt_img = read_image(GT_DIR / f"{case_id}.nii.gz")
    gt = gt > 0
    if not gt.any():
        raise RuntimeError(f"Empty GT target for {case_id}")
    selected_z = wf.select_sparse_slices(gt, 7, "even_nonempty", case_id)
    prompt = wf.make_prompt(gt, selected_z)

    linear = linear_mask_interpolation(prompt).astype(bool)
    linear[prompt] = True

    oar = np.zeros_like(gt, dtype=np.uint8)
    methods, support, _ = wf.build_methods(prompt, selected_z, gt_img.GetSpacing(), oar, "current")
    base = methods["sdf_base"].astype(bool)
    core = methods["core_only"].astype(bool)
    support_100 = support_mask(support, 1.0, prompt)

    linear_core_intersection = linear & core
    linear_core_intersection[prompt] = True

    feature_value = float(core.sum() / max(int(base.sum()), 1))
    cond = feature_value < float(rule["threshold"]) if rule["op"] == "lt" else feature_value >= float(rule["threshold"])
    chosen_source = rule["method_if_true"] if cond else rule["method_if_false"]
    if chosen_source == "linear_core_intersection":
        ours = linear_core_intersection
    elif chosen_source == "support_100":
        ours = support_100
    else:
        raise RuntimeError(f"Unsupported chosen source: {chosen_source}")
    ours[prompt] = True

    return {
        "gt": gt,
        "gt_img": gt_img,
        "prompt": prompt,
        "baseline": linear,
        "ours": ours.astype(bool),
        "selected_z": [int(z) for z in selected_z],
        "chosen_source": chosen_source,
        "rule_feature_value": feature_value,
    }


def copy_or_write_baseline(case_id: str, generated: np.ndarray, ref_image: sitk.Image, out_path: Path) -> float:
    existing_path = LINEAR_DIR / f"{case_id}.nii.gz"
    if existing_path.exists():
        existing = read_bool(existing_path)
        mismatch = float(np.mean(existing != generated)) if existing.shape == generated.shape else 1.0
        if mismatch > 0.0:
            print(f"[WARN] regenerated baseline differs from stored baseline for {case_id}: mismatch={mismatch:.6f}")
        write_like(existing, ref_image, out_path)
        return mismatch
    write_like(generated, ref_image, out_path)
    return 0.0


def normalize_ct(slice2d: np.ndarray) -> np.ndarray:
    image = np.clip(slice2d.astype(np.float32), -1000.0, 600.0)
    image = (image + 1000.0) / 1600.0
    return np.clip(image * 255.0, 0.0, 255.0).astype(np.uint8)


def mask_edge(mask: np.ndarray) -> np.ndarray:
    mask = mask.astype(bool)
    if not mask.any():
        return np.zeros(mask.shape, dtype=bool)
    eroded = ndimage.binary_erosion(mask, structure=np.ones((3, 3), dtype=bool), border_value=0)
    edge = mask ^ eroded
    return ndimage.binary_dilation(edge, structure=np.ones((2, 2), dtype=bool))


def overlay_edges(gray: np.ndarray, masks: dict[str, np.ndarray]) -> Image.Image:
    rgb = np.stack([gray, gray, gray], axis=-1).astype(np.float32)
    for key in ("baseline", "ours", "gt", "prompt"):
        edge = mask_edge(masks[key])
        if not edge.any():
            continue
        color = np.asarray(COLORS[key], dtype=np.float32)
        alpha = 0.88 if key in ("gt", "ours") else 0.78
        rgb[edge] = (1.0 - alpha) * rgb[edge] + alpha * color
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")


def draw_legend(image: Image.Image, z: int, slice_metrics: dict[str, float], prompt_slice: bool) -> Image.Image:
    pad_top = 48
    canvas = Image.new("RGB", (image.width, image.height + pad_top), (247, 248, 250))
    canvas.paste(image, (0, pad_top))
    draw = ImageDraw.Draw(canvas)
    title = (
        f"z={z:03d}  baseline zDice={fmt(slice_metrics['baseline'])}  "
        f"ours zDice={fmt(slice_metrics['ours'])}"
    )
    if prompt_slice:
        title += "  PROMPT"
    draw.text((8, 6), title, fill=(31, 35, 40))
    x = 8
    y = 28
    for label, key in (("GT", "gt"), ("Linear baseline", "baseline"), ("Ours", "ours"), ("Prompt", "prompt")):
        draw.rectangle((x, y + 2, x + 14, y + 12), fill=COLORS[key])
        draw.text((x + 18, y), label, fill=(31, 35, 40))
        x += 118 if label != "Linear baseline" else 162
    return canvas


def render_slice_png(
    ct_slice: np.ndarray,
    gt_slice: np.ndarray,
    baseline_slice: np.ndarray,
    ours_slice: np.ndarray,
    prompt_slice: np.ndarray,
    z: int,
    out_path: Path,
) -> dict[str, float]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    slice_metrics = {
        "baseline": dice_score(baseline_slice, gt_slice),
        "ours": dice_score(ours_slice, gt_slice),
    }
    image = overlay_edges(
        normalize_ct(ct_slice),
        {
            "gt": gt_slice,
            "baseline": baseline_slice,
            "ours": ours_slice,
            "prompt": prompt_slice,
        },
    )
    image = draw_legend(image, z, slice_metrics, bool(prompt_slice.any()))
    image.save(out_path)
    return slice_metrics


def write_case_html(out_dir: Path, case_id: str, rows: list[dict], case_info: dict) -> None:
    body_rows = []
    for row in rows:
        img = html.escape(row["image_rel"])
        prompt = "yes" if row["is_prompt_slice"] else ""
        body_rows.append(
            "<tr>"
            f"<td>{row['z']}</td>"
            f"<td>{prompt}</td>"
            f"<td>{fmt(row['baseline_slice_dice'])}</td>"
            f"<td>{fmt(row['ours_slice_dice'])}</td>"
            f"<td><img src=\"{img}\" loading=\"lazy\" alt=\"{html.escape(case_id)} z{row['z']}\"></td>"
            "</tr>"
        )
    case_page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(case_id)} all-slice CTV comparison</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f7f8; color: #1f2328; }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    .small {{ color: #57606a; font-size: 13px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; }}
    th, td {{ border: 1px solid #d8dee4; padding: 6px 8px; font-size: 13px; text-align: left; vertical-align: top; }}
    th {{ background: #eef1f4; position: sticky; top: 0; z-index: 1; }}
    img {{ width: min(100%, 720px); display: block; }}
    a {{ color: #0969da; }}
  </style>
</head>
<body>
  <p><a href="../index.html">Back to index</a></p>
  <h1>{html.escape(case_id)} all-slice CTV comparison</h1>
  <p class="small">
    Global Dice: linear baseline={fmt(case_info['baseline_dice'])},
    ours={fmt(case_info['ours_dice'])}, delta={fmt(case_info['delta_dice'])}.
    Prompt z: {html.escape(case_info['selected_z'])}. Ours source: {html.escape(case_info['chosen_source'])}.
  </p>
  <table>
    <thead><tr><th>z</th><th>Prompt</th><th>Baseline zDice</th><th>Ours zDice</th><th>Overlay</th></tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
</body>
</html>
"""
    case_path = out_dir / "cases" / f"{case_id}.html"
    case_path.parent.mkdir(parents=True, exist_ok=True)
    case_path.write_text(case_page)


def write_index(out_dir: Path, case_rows: list[dict], summary: dict) -> None:
    table_rows = []
    for row in case_rows:
        case_rel = f"cases/{row['case']}.html"
        table_rows.append(
            "<tr>"
            f"<td><a href=\"{case_rel}\">{html.escape(row['case'])}</a></td>"
            f"<td>{fmt(row['baseline_dice'])}</td>"
            f"<td>{fmt(row['ours_dice'])}</td>"
            f"<td>{fmt(row['delta_dice'])}</td>"
            f"<td>{fmt(row['baseline_unseen_dice'])}</td>"
            f"<td>{fmt(row['ours_unseen_dice'])}</td>"
            f"<td>{html.escape(row['chosen_source'])}</td>"
            f"<td>{html.escape(row['selected_z'])}</td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Best CTV preprocessing method vs best baseline</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f7f8; color: #1f2328; }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    .small {{ color: #57606a; font-size: 13px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; }}
    th, td {{ border: 1px solid #d8dee4; padding: 6px 8px; font-size: 13px; text-align: left; }}
    th {{ background: #eef1f4; position: sticky; top: 0; z-index: 1; }}
    a {{ color: #0969da; }}
    .metric {{ display: inline-block; margin-right: 18px; }}
  </style>
</head>
<body>
  <h1>Best CTV preprocessing method vs best baseline</h1>
  <p class="small">
    Ours: train-calibrated support-intersection rule. Baseline: K=7 linear mask interpolation.
    Both use the same simulated sparse full-slice CTV prompts.
  </p>
  <p class="small">
    <span class="metric">n={summary['n']}</span>
    <span class="metric">baseline Dice={fmt(summary['baseline_mean'])} +/- {fmt(summary['baseline_std'])}</span>
    <span class="metric">ours Dice={fmt(summary['ours_mean'])} +/- {fmt(summary['ours_std'])}</span>
    <span class="metric">mean delta={fmt(summary['delta_mean'])}</span>
    <span class="metric">improved={summary['improved']}/{summary['n']}</span>
  </p>
  <table>
    <thead>
      <tr>
        <th>Case</th><th>Baseline Dice</th><th>Ours Dice</th><th>Delta</th>
        <th>Baseline Unseen Dice</th><th>Ours Unseen Dice</th><th>Ours source</th><th>Prompt z</th>
      </tr>
    </thead>
    <tbody>{''.join(table_rows)}</tbody>
  </table>
</body>
</html>
"""
    (out_dir / "index.html").write_text(document)


def summarize_rows(rows: list[dict]) -> dict:
    baseline = np.asarray([float(r["baseline_dice"]) for r in rows], dtype=float)
    ours = np.asarray([float(r["ours_dice"]) for r in rows], dtype=float)
    delta = ours - baseline
    return {
        "n": int(len(rows)),
        "baseline_mean": float(baseline.mean()),
        "baseline_std": float(baseline.std()),
        "ours_mean": float(ours.mean()),
        "ours_std": float(ours.std()),
        "delta_mean": float(delta.mean()),
        "delta_std": float(delta.std()),
        "improved": int((delta > 0).sum()),
        "worse": int((delta < 0).sum()),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", default=str(ROOT / "reports/best_ctv_method_vs_best_baseline_20260603"))
    parser.add_argument("--max_cases", type=int, default=None)
    parser.add_argument("--case", action="append", default=None, help="Specific case ID to export. Can be passed multiple times.")
    parser.add_argument("--skip_existing_slices", action="store_true")
    parser.add_argument("--skip_slice_pngs", action="store_true", help="Compute slice metrics without rendering PNG overlays.")
    parser.add_argument("--skip_html", action="store_true", help="Skip writing index.html and per-case HTML pages.")
    parser.add_argument(
        "--use_existing_masks",
        action="store_true",
        help="Reuse existing best-method NIfTI masks instead of regenerating SDF candidates. Intended for fast audit smoke tests.",
    )
    parser.add_argument(
        "--skip_nifti_write",
        action="store_true",
        help="Do not write NIfTI masks into out_dir. Requires --use_existing_masks and references the existing masks in the CSV output.",
    )
    args = parser.parse_args()
    if args.skip_nifti_write and not args.use_existing_masks:
        raise RuntimeError("--skip_nifti_write requires --use_existing_masks")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rule = load_rule()
    expected_ours_dice = load_expected_ours_dice()
    existing_rows = load_existing_export_rows() if args.use_existing_masks else {}
    cases = case_names(GT_DIR)
    if args.case:
        requested = list(dict.fromkeys(args.case))
        available = set(cases)
        missing = [case for case in requested if case not in available]
        if missing:
            raise RuntimeError(f"Requested cases not found in {GT_DIR}: {missing}")
        cases = requested
    if args.max_cases is not None:
        cases = cases[: args.max_cases]

    case_rows: list[dict] = []
    slice_rows: list[dict] = []

    nii_ours_dir = out_dir / "nii" / "ours_train_calibrated_support_intersection_rule"
    nii_baseline_dir = out_dir / "nii" / "baseline_linear_mask_interpolation_k7"
    nii_prompt_dir = out_dir / "nii" / "sparse_prompt_k7_even_nonempty"

    for index, case_id in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case_id}", flush=True)
        ct = None
        if not args.skip_slice_pngs:
            ct, _ = read_image(CT_DIR / f"{case_id}_0000.nii.gz")
        masks = load_existing_masks(case_id, existing_rows) if args.use_existing_masks else build_masks(case_id, rule)
        gt = masks["gt"]
        gt_img = masks["gt_img"]
        prompt = masks["prompt"]
        baseline = masks["baseline"]
        ours = masks["ours"]
        selected_z = masks["selected_z"]
        pzm = prompt_z_mask(prompt)

        if args.skip_nifti_write:
            ours_path = EXISTING_EXPORT_DIR / "nii/ours_train_calibrated_support_intersection_rule" / f"{case_id}.nii.gz"
            baseline_path = EXISTING_EXPORT_DIR / "nii/baseline_linear_mask_interpolation_k7" / f"{case_id}.nii.gz"
            prompt_path = EXISTING_EXPORT_DIR / "nii/sparse_prompt_k7_even_nonempty" / f"{case_id}.nii.gz"
            baseline_mismatch = 0.0
        else:
            ours_path = nii_ours_dir / f"{case_id}.nii.gz"
            baseline_path = nii_baseline_dir / f"{case_id}.nii.gz"
            prompt_path = nii_prompt_dir / f"{case_id}.nii.gz"
            write_like(ours, gt_img, ours_path)
        if args.skip_nifti_write:
            pass
        elif args.use_existing_masks:
            write_like(baseline, gt_img, baseline_path)
            baseline_mismatch = 0.0
        else:
            baseline_mismatch = copy_or_write_baseline(case_id, baseline, gt_img, baseline_path)
        if not args.skip_nifti_write:
            write_like(prompt, gt_img, prompt_path)

        baseline_saved = read_bool(baseline_path)
        baseline_dice = dice_score(baseline_saved, gt)
        ours_dice = dice_score(ours, gt)
        baseline_unseen = dice_score(baseline_saved[~pzm], gt[~pzm])
        ours_unseen = dice_score(ours[~pzm], gt[~pzm])
        expected = expected_ours_dice.get(case_id)
        if expected is None:
            raise RuntimeError(f"Missing expected Ours metric for {case_id}")
        if abs(ours_dice - expected) > 1e-10:
            raise RuntimeError(f"Ours Dice mismatch for {case_id}: regenerated={ours_dice}, expected={expected}")

        case_row = {
            "case": case_id,
            "baseline_method": "linear_mask_interpolation_k7",
            "ours_method": "train_calibrated_support_intersection_rule",
            "baseline_dice": baseline_dice,
            "ours_dice": ours_dice,
            "delta_dice": ours_dice - baseline_dice,
            "baseline_unseen_dice": baseline_unseen,
            "ours_unseen_dice": ours_unseen,
            "chosen_source": str(masks["chosen_source"]),
            "rule_feature": rule["feature"],
            "rule_feature_value": float(masks["rule_feature_value"]),
            "rule_threshold": float(rule["threshold"]),
            "selected_z": ";".join(str(z) for z in selected_z),
            "n_slices": int(gt.shape[0]),
            "ct_path": str((CT_DIR / f"{case_id}_0000.nii.gz").relative_to(ROOT)),
            "gt_path": str((GT_DIR / f"{case_id}.nii.gz").relative_to(ROOT)),
            "baseline_nii": str(baseline_path.relative_to(ROOT)),
            "ours_nii": str(ours_path.relative_to(ROOT)),
            "prompt_nii": str(prompt_path.relative_to(ROOT)),
            "baseline_regen_mismatch_fraction": baseline_mismatch,
        }
        case_rows.append(case_row)

        case_slice_rows: list[dict] = []
        for z in range(gt.shape[0]):
            image_rel = f"../slices/{case_id}/z{z:03d}.png"
            out_png = out_dir / "slices" / case_id / f"z{z:03d}.png"
            if args.skip_slice_pngs:
                slice_metrics = {
                    "baseline": dice_score(baseline_saved[z], gt[z]),
                    "ours": dice_score(ours[z], gt[z]),
                }
            elif args.skip_existing_slices and out_png.exists():
                slice_metrics = {
                    "baseline": dice_score(baseline_saved[z], gt[z]),
                    "ours": dice_score(ours[z], gt[z]),
                }
            else:
                slice_metrics = render_slice_png(
                    ct[z],
                    gt[z],
                    baseline_saved[z],
                    ours[z],
                    prompt[z],
                    z,
                    out_png,
                )
            row = {
                "case": case_id,
                "z": z,
                "is_prompt_slice": int(bool(prompt[z].any())),
                "gt_voxels": int(gt[z].sum()),
                "baseline_voxels": int(baseline_saved[z].sum()),
                "ours_voxels": int(ours[z].sum()),
                "prompt_voxels": int(prompt[z].sum()),
                "baseline_slice_dice": slice_metrics["baseline"],
                "ours_slice_dice": slice_metrics["ours"],
                "image_rel": image_rel,
            }
            case_slice_rows.append(row)
            slice_rows.append(row)

        case_info = dict(case_row)
        case_info["selected_z"] = case_row["selected_z"]
        if not args.skip_html:
            write_case_html(out_dir, case_id, case_slice_rows, case_info)

    summary = summarize_rows(case_rows)
    summary["rule"] = rule

    write_csv(out_dir / "per_case_dice_comparison.csv", case_rows)
    write_csv(out_dir / "slice_dice_comparison.csv", slice_rows)
    write_csv(out_dir / "manifest.csv", case_rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    if not args.skip_html:
        write_index(out_dir, case_rows, summary)

    if not args.skip_html:
        print("Wrote", out_dir / "index.html")
    print("Wrote", out_dir / "per_case_dice_comparison.csv")
    print("Wrote", out_dir / "slice_dice_comparison.csv")
    print("Wrote", out_dir / "manifest.csv")
    print("Wrote", out_dir / "summary.json")
    print("Referenced existing NIfTI dirs:" if args.skip_nifti_write else "Wrote NIfTI dirs:")
    print("  ", nii_ours_dir)
    print("  ", nii_baseline_dir)
    print("  ", nii_prompt_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
