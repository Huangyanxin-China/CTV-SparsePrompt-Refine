#!/usr/bin/env python3
"""Generate manuscript-ready qualitative comparison figures from NIfTI outputs.

This script intentionally depends only on nibabel and numpy because the current
server image stack is minimal. It writes RGB PNG files directly with zlib.
"""

from __future__ import annotations

import csv
import json
import os
import struct
import zlib
from pathlib import Path

import nibabel as nib
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
CASE = os.environ.get("CTV_EXAMPLE_CASE", "EXAMPLE_CASE")
OUT_DIR = PROJECT / "manuscript_pr_biomedical_data_refine_20260603" / "figures"


FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["000", "000", "000", "000", "000", "110", "110"],
    ":": ["000", "110", "110", "000", "110", "110", "000"],
    "=": ["00000", "11111", "00000", "11111", "00000", "00000", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "(": ["001", "010", "100", "100", "100", "010", "001"],
    ")": ["100", "010", "001", "001", "001", "010", "100"],
}


def write_png(path: Path, rgb: np.ndarray) -> None:
    rgb = np.asarray(rgb, dtype=np.uint8)
    h, w, c = rgb.shape
    assert c == 3

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def load(path: str | Path) -> np.ndarray:
    return np.asarray(nib.load(str(PROJECT / path)).get_fdata())


def mask(path: str | Path) -> np.ndarray:
    return load(path) > 0.5


def dice(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(bool)
    b = b.astype(bool)
    denom = a.sum() + b.sum()
    if denom == 0:
        return 1.0
    return 2.0 * np.logical_and(a, b).sum() / denom


def border(mask2d: np.ndarray, thickness: int = 2) -> np.ndarray:
    m = mask2d.astype(bool)
    if not m.any():
        return m
    padded = np.pad(m, 1, constant_values=False)
    eroded = (
        padded[1:-1, 1:-1]
        & padded[:-2, 1:-1]
        & padded[2:, 1:-1]
        & padded[1:-1, :-2]
        & padded[1:-1, 2:]
    )
    edge = m & ~eroded
    out = edge.copy()
    for _ in range(max(0, thickness - 1)):
        p = np.pad(out, 1, constant_values=False)
        out = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return out


def resize_nn(arr: np.ndarray, h: int, w: int) -> np.ndarray:
    ys = np.linspace(0, arr.shape[0] - 1, h).round().astype(int)
    xs = np.linspace(0, arr.shape[1] - 1, w).round().astype(int)
    return arr[np.ix_(ys, xs)]


def draw_text(img: np.ndarray, text: str, y: int, x: int, color=(255, 255, 255), scale: int = 2) -> None:
    text = text.upper()
    cx = x
    for ch in text:
        glyph = FONT.get(ch, FONT[" "])
        gh = len(glyph)
        gw = len(glyph[0])
        for gy in range(gh):
            for gx in range(gw):
                if glyph[gy][gx] == "1":
                    yy = y + gy * scale
                    xx = cx + gx * scale
                    img[yy : yy + scale, xx : xx + scale] = color
        cx += (gw + 1) * scale


def panel(
    ct2d: np.ndarray,
    gt2d: np.ndarray,
    pred2d: np.ndarray | None,
    prompt2d: np.ndarray | None,
    crop: tuple[int, int, int, int],
    label: str,
    size: int = 290,
) -> np.ndarray:
    x0, x1, y0, y1 = crop
    ct = ct2d[x0:x1, y0:y1]
    base = np.clip((ct - (-1000.0)) / 1600.0, 0, 1)
    rgb = np.repeat((base * 255).astype(np.uint8)[..., None], 3, axis=2)

    gt = gt2d[x0:x1, y0:y1]
    rgb[gt] = (0.75 * rgb[gt] + 0.25 * np.array([0, 190, 70])).astype(np.uint8)
    rgb[border(gt, 2)] = np.array([0, 255, 80], dtype=np.uint8)

    if prompt2d is not None and prompt2d.any():
        pr = prompt2d[x0:x1, y0:y1]
        rgb[pr] = (0.70 * rgb[pr] + 0.30 * np.array([255, 210, 0])).astype(np.uint8)
        rgb[border(pr, 2)] = np.array([255, 230, 0], dtype=np.uint8)

    if pred2d is not None:
        pred = pred2d[x0:x1, y0:y1]
        rgb[pred] = (0.72 * rgb[pred] + 0.28 * np.array([230, 0, 255])).astype(np.uint8)
        rgb[border(pred, 2)] = np.array([255, 0, 255], dtype=np.uint8)

    rgb = resize_nn(rgb, size, size)
    canvas = np.zeros((size + 34, size, 3), dtype=np.uint8) + 18
    canvas[34:, :, :] = rgb
    draw_text(canvas, label, 10, 10, color=(255, 255, 255), scale=2)
    return canvas


def grid(panels: list[np.ndarray], ncols: int, pad: int = 12) -> np.ndarray:
    ph, pw, _ = panels[0].shape
    nrows = int(np.ceil(len(panels) / ncols))
    out = np.zeros((nrows * ph + (nrows + 1) * pad, ncols * pw + (ncols + 1) * pad, 3), dtype=np.uint8) + 255
    for i, p in enumerate(panels):
        r, c = divmod(i, ncols)
        y = pad + r * (ph + pad)
        x = pad + c * (pw + pad)
        out[y : y + ph, x : x + pw] = p
    return out


def read_metric_csv(path: str, case: str, method: str | None = None) -> dict[str, str] | None:
    with (PROJECT / path).open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("case") != case:
                continue
            if method is None or row.get("method") == method:
                return row
    return None


def find_slice(gt: np.ndarray, prompt: np.ndarray, linear: np.ndarray, support: np.ndarray, refine: np.ndarray) -> int:
    max_area = gt.sum(axis=(0, 1)).max()
    best = None
    for z in range(gt.shape[2]):
        area = gt[:, :, z].sum()
        if area < max_area * 0.35:
            continue
        if prompt[:, :, z].sum() > 0:
            continue
        lin_d = dice(linear[:, :, z], gt[:, :, z])
        sup_d = dice(support[:, :, z], gt[:, :, z])
        ref_d = dice(refine[:, :, z], gt[:, :, z])
        score = (sup_d - lin_d) + 0.5 * (ref_d - lin_d) + 0.000001 * area
        cand = (score, z, lin_d, sup_d, ref_d, area)
        if best is None or cand > best:
            best = cand
    if best is None:
        return int(np.argmax(gt.sum(axis=(0, 1))))
    return int(best[1])


def make_crop(gt2d: np.ndarray, prompt2d: np.ndarray, margin: int = 58) -> tuple[int, int, int, int]:
    union = gt2d | prompt2d
    xs, ys = np.where(union)
    if len(xs) == 0:
        return 0, gt2d.shape[0], 0, gt2d.shape[1]
    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    side = max(x1 - x0, y1 - y0) + 2 * margin
    side = min(max(side, 120), min(gt2d.shape))
    x0 = max(0, cx - side // 2)
    y0 = max(0, cy - side // 2)
    x1 = min(gt2d.shape[0], x0 + side)
    y1 = min(gt2d.shape[1], y0 + side)
    x0 = max(0, x1 - side)
    y0 = max(0, y1 - side)
    return int(x0), int(x1), int(y0), int(y1)


def main() -> None:
    case = CASE
    ct = load(f"nnunet_runs/raw/Dataset015_CTV_Dataset004Split/imagesTs/{case}_0000.nii.gz")
    gt = mask(f"nnunet_runs/raw/Dataset015_CTV_Dataset004Split/labelsTs/{case}.nii.gz")
    prompt = mask(f"reports/best_ctv_method_vs_best_baseline_20260603/nii/sparse_prompt_k7_even_nonempty/{case}.nii.gz")
    linear = mask(f"reports/best_ctv_method_vs_best_baseline_20260603/nii/baseline_linear_mask_interpolation_k7/{case}.nii.gz")
    support = mask(f"reports/best_ctv_method_vs_best_baseline_20260603/nii/ours_train_calibrated_support_intersection_rule/{case}.nii.gz")
    refine = mask(f"results/ctv_pseudo_refine_net_k7_oarroi_fastmargin_supervised_gpu1/predictions_test/{case}.nii.gz")

    method_masks = {
        "NNUNET": mask(f"external_runs/nnunet/nnunet_3d_fullres_folds012_final/ctv/{case}.nii.gz"),
        "DIFFUNET": mask(f"external_runs/diffunet/ctv/predictions/{case}.nii.gz"),
        "SAM CT": mask(f"external_runs/sammed3d_nonoracle/ctv_ct_heuristic_click1/{case}.nii.gz"),
        "SAM K7": mask(f"external_runs/sammed3d_sparse_prompt/ctv_k7_even_nonempty_click7/{case}.nii.gz"),
        "LINEAR": linear,
        "SUPPORT": support,
        "REFINE": refine,
    }
    ablation_masks = {
        "LINEAR": linear,
        "SDF BASE": mask(f"results/core_envelope_oar_refine_k7_current/predictions/sdf_base/{case}.nii.gz"),
        "SDF CORE": mask(f"results/core_envelope_oar_refine_k7_current/predictions/core_only/{case}.nii.gz"),
        "SUPPORT": support,
        "REFINE": refine,
    }

    z = find_slice(gt, prompt, linear, support, refine)
    crop = make_crop(gt[:, :, z], prompt[:, :, z])

    metrics = {
        "NNUNET": float(read_metric_csv("external_runs/metrics/nnunet_3d_fullres_folds012_final/ctv/per_case.csv", case)["dice"]),
        "DIFFUNET": float(read_metric_csv("external_runs/metrics/diffunet/ctv/per_case.csv", case)["dice"]),
        "SAM CT": float(read_metric_csv("external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/ctv/per_case.csv", case)["dice"]),
        "SAM K7": float(read_metric_csv("external_runs/metrics/sammed3d_sparse_prompt_k7_even_nonempty_click7/ctv/per_case.csv", case)["dice"]),
        "LINEAR": float(read_metric_csv("reports/best_ctv_method_vs_best_baseline_20260603/per_case_dice_comparison.csv", case)["baseline_dice"]),
        "SUPPORT": float(read_metric_csv("reports/best_ctv_method_vs_best_baseline_20260603/per_case_dice_comparison.csv", case)["ours_dice"]),
        "REFINE": float(read_metric_csv("results/ctv_pseudo_refine_net_k7_oarroi_fastmargin_supervised_gpu1/test_extended_metrics.csv", case)["dice"]),
    }
    for name, arr in ablation_masks.items():
        metrics.setdefault(name, dice(arr, gt))
    metrics["SDF BASE"] = dice(ablation_masks["SDF BASE"], gt)
    metrics["SDF CORE"] = dice(ablation_masks["SDF CORE"], gt)

    method_panels = [
        panel(ct[:, :, z], gt[:, :, z], None, prompt[:, :, z], crop, "GT UNSEEN Z"),
    ]
    for name in ["NNUNET", "DIFFUNET", "SAM CT", "SAM K7", "LINEAR", "SUPPORT", "REFINE"]:
        method_panels.append(
            panel(ct[:, :, z], gt[:, :, z], method_masks[name][:, :, z], None, crop, f"{name} D {metrics[name]:.3f}")
        )
    method_grid = grid(method_panels, ncols=4)
    method_path = OUT_DIR / f"method_visual_comparison_{case}.png"
    write_png(method_path, method_grid)

    ablation_panels = [
        panel(ct[:, :, z], gt[:, :, z], None, prompt[:, :, z], crop, "GT UNSEEN Z"),
    ]
    for name in ["LINEAR", "SDF BASE", "SDF CORE", "SUPPORT", "REFINE"]:
        ablation_panels.append(
            panel(ct[:, :, z], gt[:, :, z], ablation_masks[name][:, :, z], None, crop, f"{name} D {metrics[name]:.3f}")
        )
    ablation_grid = grid(ablation_panels, ncols=3)
    ablation_path = OUT_DIR / f"ablation_visual_progression_{case}.png"
    write_png(ablation_path, ablation_grid)

    manifest = {
        "case": case,
        "selected_slice_z": z,
        "crop_x0_x1_y0_y1": crop,
        "colors": {
            "GT": "green contour/fill",
            "Prediction": "magenta contour/fill",
            "Sparse prompt": "yellow contour/fill",
        },
        "method_comparison_figure": str(method_path.relative_to(PROJECT)),
        "ablation_figure": str(ablation_path.relative_to(PROJECT)),
        "dice_values": metrics,
    }
    manifest_path = OUT_DIR / f"visual_figure_manifest_{case}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
