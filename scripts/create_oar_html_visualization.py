#!/usr/bin/env python3
"""Create an HTML visual review pack for OAR segmentation baselines.

The execution environment used for this project does not always provide
matplotlib, Pillow, or SimpleITK. This script therefore uses only nibabel,
numpy, and the Python standard library to write RGB PNG files.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import struct
import zlib
from pathlib import Path

import nibabel as nib
import numpy as np


ROOT = Path(__file__).resolve().parents[1]

CT_DIR = Path(
    "/share3/home/huangyanxin/nnUNet/DATASET/nnUNet_raw/"
    "Dataset004_ThoracicOARCTV_OneCaseTrain/imagesTs"
)
GT_DIR = ROOT / "nnunet_runs/raw/Dataset014_ThoracicOAR_Dataset004Split/labelsTs"

ORGANS = [
    (1, "lung"),
    (2, "heart"),
    (3, "spinal"),
    (4, "esophagus"),
]

METHODS = [
    {
        "key": "nnunet",
        "name": "nnU-Net",
        "path": ROOT / "external_runs/nnunet/nnunet_3d_fullres_folds234_final/oar",
        "metrics": ROOT / "external_runs/metrics/nnunet_3d_fullres_folds234_final/oar/per_case.csv",
        "note": "fully automatic",
    },
    {
        "key": "diffunet",
        "name": "DiffUNet",
        "path": ROOT / "external_runs/diffunet/oar/predictions",
        "metrics": ROOT / "external_runs/metrics/diffunet/oar/per_case.csv",
        "note": "fully automatic",
    },
    {
        "key": "sam_ct",
        "name": "SAM-Med3D CT prompt",
        "path": ROOT / "external_runs/sammed3d_nonoracle/oar_ct_heuristic_click1",
        "metrics": ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/oar/per_case.csv",
        "note": "automatic CT-derived prompt",
    },
    {
        "key": "sam_oracle",
        "name": "SAM-Med3D oracle",
        "path": ROOT / "external_runs/sammed3d/predictions/oar_click10",
        "metrics": ROOT / "external_runs/metrics/sammed3d_click10/oar/per_case.csv",
        "note": "full-GT prompt, diagnostic oracle",
    },
]


def read_nifti(path: Path) -> np.ndarray:
    return np.asarray(nib.load(str(path)).dataobj)


def normalize_ct(slice2d: np.ndarray) -> np.ndarray:
    image = np.clip(slice2d.astype(np.float32), -1000.0, 600.0)
    image = (image + 1000.0) / 1600.0
    return np.clip(image * 255.0, 0, 255).astype(np.uint8)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png_rgb(path: Path, rgb: np.ndarray) -> None:
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("write_png_rgb expects a uint8 RGB image")
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))
    data = b"\x89PNG\r\n\x1a\n"
    data += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    data += png_chunk(b"IDAT", zlib.compress(raw, level=6))
    data += png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def resize_nearest(image: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    in_h, in_w = image.shape[:2]
    if in_h == out_h and in_w == out_w:
        return image.copy()
    y_idx = np.minimum((np.arange(out_h) * in_h // out_h), in_h - 1)
    x_idx = np.minimum((np.arange(out_w) * in_w // out_w), in_w - 1)
    return image[y_idx[:, None], x_idx[None, :]]


def mask_boundary(mask: np.ndarray) -> np.ndarray:
    mask = mask.astype(bool)
    if mask.sum() == 0:
        return mask
    interior = mask.copy()
    interior[1:, :] &= mask[:-1, :]
    interior[:-1, :] &= mask[1:, :]
    interior[:, 1:] &= mask[:, :-1]
    interior[:, :-1] &= mask[:, 1:]
    return mask & ~interior


def dilate2d(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    out = mask.astype(bool).copy()
    src = out.copy()
    for _ in range(radius):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        grown[1:, 1:] |= out[:-1, :-1]
        grown[:-1, :-1] |= out[1:, 1:]
        grown[1:, :-1] |= out[:-1, 1:]
        grown[:-1, 1:] |= out[1:, :-1]
        out = grown
    return out | src


def bbox_from_masks(masks: list[np.ndarray], pad: int = 32) -> tuple[slice, slice]:
    union = np.zeros_like(masks[0], dtype=bool)
    for mask in masks:
        union |= mask.astype(bool)
    pts = np.argwhere(union)
    if pts.size == 0:
        return slice(None), slice(None)
    y0, x0 = pts.min(axis=0)
    y1, x1 = pts.max(axis=0) + 1
    h, w = union.shape
    return slice(max(0, y0 - pad), min(h, y1 + pad)), slice(max(0, x0 - pad), min(w, x1 + pad))


def make_square_crop(image: np.ndarray, masks: list[np.ndarray]) -> tuple[np.ndarray, list[np.ndarray]]:
    h, w = image.shape
    size = max(h, w)
    y_pad = size - h
    x_pad = size - w
    before_y, after_y = y_pad // 2, y_pad - y_pad // 2
    before_x, after_x = x_pad // 2, x_pad - x_pad // 2
    image_out = np.pad(image, ((before_y, after_y), (before_x, after_x)), mode="edge")
    masks_out = [
        np.pad(mask, ((before_y, after_y), (before_x, after_x)), mode="constant", constant_values=False)
        for mask in masks
    ]
    return image_out, masks_out


def render_panel(
    ct_slice: np.ndarray,
    gt_mask: np.ndarray,
    pred_mask: np.ndarray | None,
    crop_y: slice,
    crop_x: slice,
    panel_size: int,
) -> np.ndarray:
    ct_crop = normalize_ct(ct_slice[crop_y, crop_x])
    gt_crop = gt_mask[crop_y, crop_x].astype(bool)
    pred_crop = None if pred_mask is None else pred_mask[crop_y, crop_x].astype(bool)
    mask_list = [gt_crop] + ([] if pred_crop is None else [pred_crop])
    ct_crop, resized_masks_source = make_square_crop(ct_crop, mask_list)
    gt_crop = resized_masks_source[0]
    pred_crop = None if pred_crop is None else resized_masks_source[1]

    base = resize_nearest(ct_crop, panel_size, panel_size)
    rgb = np.stack([base, base, base], axis=-1)
    gt_resized = resize_nearest(gt_crop.astype(np.uint8), panel_size, panel_size).astype(bool)
    gt_line = dilate2d(mask_boundary(gt_resized), radius=1)
    rgb[gt_line] = np.array([0, 210, 100], dtype=np.uint8)
    if pred_crop is not None:
        pred_resized = resize_nearest(pred_crop.astype(np.uint8), panel_size, panel_size).astype(bool)
        pred_line = dilate2d(mask_boundary(pred_resized), radius=1)
        rgb[pred_line] = np.array([230, 45, 60], dtype=np.uint8)
    return rgb


def dice_binary(pred: np.ndarray, gt: np.ndarray) -> float:
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    denom = int(pred.sum()) + int(gt.sum())
    if denom == 0:
        return 1.0
    return float(2.0 * np.logical_and(pred, gt).sum() / denom)


def choose_organ_slice(gt: np.ndarray, class_id: int) -> int:
    area = (gt == class_id).sum(axis=(0, 1))
    if int(area.max()) == 0:
        return gt.shape[2] // 2
    return int(np.argmax(area))


def load_metrics() -> dict[tuple[str, str, int], dict[str, str]]:
    metrics: dict[tuple[str, str, int], dict[str, str]] = {}
    for spec in METHODS:
        path = spec["metrics"]
        if not path.exists():
            continue
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                key = (spec["key"], row["case"], int(row["class_id"]))
                metrics[key] = row
    return metrics


def fmt_metric(value: str | float | None) -> str:
    if value is None or value == "" or str(value).lower() == "nan":
        return "--"
    return f"{float(value):.3f}"


def available_methods() -> list[dict[str, object]]:
    found = []
    for spec in METHODS:
        count = len(list(Path(spec["path"]).glob("*.nii.gz")))
        if count:
            found.append({**spec, "count": count})
    return found


def render_case(case_id: str, out_dir: Path, panel_size: int, metrics: dict[tuple[str, str, int], dict[str, str]]) -> list[dict[str, object]]:
    ct_path = CT_DIR / f"{case_id}_0000.nii.gz"
    gt_path = GT_DIR / f"{case_id}.nii.gz"
    ct = read_nifti(ct_path)
    gt = read_nifti(gt_path).astype(np.uint8)
    methods = available_methods()
    pred_arrays = {
        str(spec["key"]): read_nifti(Path(spec["path"]) / f"{case_id}.nii.gz").astype(np.uint8)
        for spec in methods
        if (Path(spec["path"]) / f"{case_id}.nii.gz").exists()
    }

    rows = []
    for class_id, organ in ORGANS:
        z = choose_organ_slice(gt, class_id)
        gt2d = gt[:, :, z] == class_id
        crop_masks = [gt2d]
        for key, pred in pred_arrays.items():
            crop_masks.append(pred[:, :, z] == class_id)
        crop_y, crop_x = bbox_from_masks(crop_masks, pad=34)

        gt_panel = render_panel(ct[:, :, z], gt2d, None, crop_y, crop_x, panel_size)
        gt_rel = f"assets/{case_id}/{organ}_GT.png"
        write_png_rgb(out_dir / gt_rel, gt_panel)

        method_cells = {}
        for spec in methods:
            key = str(spec["key"])
            pred = pred_arrays.get(key)
            if pred is None:
                continue
            pred_mask = pred[:, :, z] == class_id
            panel = render_panel(ct[:, :, z], gt2d, pred_mask, crop_y, crop_x, panel_size)
            rel = f"assets/{case_id}/{organ}_{key}.png"
            write_png_rgb(out_dir / rel, panel)
            metric_row = metrics.get((key, case_id, class_id))
            method_cells[key] = {
                "image": rel,
                "dice": fmt_metric(metric_row.get("dice") if metric_row else dice_binary(pred == class_id, gt == class_id)),
                "hd95": fmt_metric(metric_row.get("hd95") if metric_row else None),
            }

        rows.append(
            {
                "case": case_id,
                "organ": organ,
                "class_id": class_id,
                "z": z,
                "gt_image": gt_rel,
                "methods": method_cells,
            }
        )
    return rows


def write_index(out_dir: Path, case_rows: dict[str, list[dict[str, object]]], methods: list[dict[str, object]]) -> None:
    method_headers = "".join(
        f"<th>{html.escape(str(spec['name']))}<br><span class=\"sub\">{html.escape(str(spec['note']))}</span></th>"
        for spec in methods
    )
    case_blocks = []
    for case_id, rows in case_rows.items():
        body_rows = []
        for row in rows:
            method_cells = []
            for spec in methods:
                key = str(spec["key"])
                cell = row["methods"].get(key)  # type: ignore[index]
                if not cell:
                    method_cells.append("<td class=\"missing\">missing</td>")
                    continue
                method_cells.append(
                    "<td>"
                    f"<img src=\"{html.escape(cell['image'])}\" loading=\"lazy\" alt=\"{html.escape(case_id)} {html.escape(row['organ'])} {html.escape(key)}\">"
                    f"<div class=\"metric\">DSC={cell['dice']} | HD95={cell['hd95']}</div>"
                    "</td>"
                )
            body_rows.append(
                "<tr>"
                f"<td class=\"organ\">{html.escape(str(row['organ']))}<br><span class=\"sub\">z={row['z']}</span></td>"
                f"<td><img src=\"{html.escape(str(row['gt_image']))}\" loading=\"lazy\" alt=\"{html.escape(case_id)} {html.escape(str(row['organ']))} GT\">"
                "<div class=\"metric\">GT boundary</div></td>"
                + "".join(method_cells)
                + "</tr>"
            )
        case_blocks.append(
            f"<section><h2>{html.escape(case_id)}</h2>"
            "<table><thead><tr><th>Organ</th><th>GT</th>"
            + method_headers
            + "</tr></thead><tbody>"
            + "".join(body_rows)
            + "</tbody></table></section>"
        )

    method_note = ", ".join(f"{spec['name']} ({spec['count']} files)" for spec in methods)
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>OAR Segmentation Test-Set Visualization</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f7f8; color: #1f2328; }}
    h1 {{ font-size: 24px; margin-bottom: 4px; }}
    h2 {{ margin-top: 28px; font-size: 18px; }}
    p {{ margin: 6px 0 12px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; margin-bottom: 22px; table-layout: fixed; }}
    th, td {{ border: 1px solid #d8dee4; padding: 6px; text-align: center; vertical-align: top; font-size: 12px; }}
    th {{ background: #eef1f4; position: sticky; top: 0; z-index: 1; }}
    img {{ width: 100%; max-width: 190px; border: 1px solid #d8dee4; background: #000; }}
    .small, .sub {{ color: #57606a; font-size: 12px; font-weight: normal; }}
    .organ {{ font-weight: bold; width: 90px; }}
    .metric {{ color: #24292f; font-size: 11px; margin-top: 3px; }}
    .legend {{ display: inline-block; padding: 3px 8px; margin-right: 8px; border-radius: 4px; background: #fff; border: 1px solid #d8dee4; }}
    .gt {{ color: rgb(0, 160, 70); font-weight: bold; }}
    .pred {{ color: rgb(210, 20, 45); font-weight: bold; }}
    .missing {{ color: #8c959f; }}
  </style>
</head>
<body>
  <h1>OAR Segmentation Test-Set Visualization</h1>
  <p class="small">Each row uses the axial slice with the largest GT area for that organ. Method panels overlay <span class="legend gt">green GT boundary</span> and <span class="legend pred">red prediction boundary</span> on the same CT crop.</p>
  <p class="small">Included methods: {html.escape(method_note)}. SAM-Med3D oracle uses full-GT prompts and is diagnostic only. U-Mamba is not shown because no complete OAR test NIfTI predictions were found.</p>
  {''.join(case_blocks)}
</body>
</html>
"""
    (out_dir / "index.html").write_text(document)


def write_summary(out_dir: Path, case_rows: dict[str, list[dict[str, object]]], methods: list[dict[str, object]]) -> None:
    with (out_dir / "per_case_organ_metrics.csv").open("w", newline="") as f:
        fieldnames = ["case", "organ", "class_id", "z"]
        for spec in methods:
            fieldnames.extend([f"{spec['key']}_dice", f"{spec['key']}_hd95"])
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rows in case_rows.values():
            for row in rows:
                out = {
                    "case": row["case"],
                    "organ": row["organ"],
                    "class_id": row["class_id"],
                    "z": row["z"],
                }
                for spec in methods:
                    key = str(spec["key"])
                    cell = row["methods"].get(key)  # type: ignore[index]
                    out[f"{key}_dice"] = cell["dice"] if cell else ""
                    out[f"{key}_hd95"] = cell["hd95"] if cell else ""
                writer.writerow(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", default=str(ROOT / "reports/html_oar_visualization"))
    parser.add_argument("--panel_size", type=int, default=192)
    parser.add_argument("--max_cases", type=int, default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = load_metrics()
    methods = available_methods()
    case_ids = sorted(path.name[:-7] for path in GT_DIR.glob("*.nii.gz"))
    if args.max_cases is not None:
        case_ids = case_ids[: args.max_cases]

    case_rows: dict[str, list[dict[str, object]]] = {}
    for idx, case_id in enumerate(case_ids, 1):
        print(f"[{idx}/{len(case_ids)}] Rendering {case_id}")
        case_rows[case_id] = render_case(case_id, out_dir, args.panel_size, metrics)

    write_index(out_dir, case_rows, methods)
    write_summary(out_dir, case_rows, methods)
    manifest = {
        "cases": len(case_ids),
        "organs": [name for _, name in ORGANS],
        "methods": [{k: str(v) for k, v in spec.items() if k != "metrics"} for spec in methods],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Wrote", out_dir / "index.html")
    print("Wrote", out_dir / "per_case_organ_metrics.csv")


if __name__ == "__main__":
    main()
