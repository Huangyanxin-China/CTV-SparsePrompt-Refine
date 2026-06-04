from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from skimage import measure


ROOT = Path(__file__).resolve().parent
NNUNET_ROOT = ROOT / "nnUNet_raw_GTV_CTV_Organ"
CTV_DIR = NNUNET_ROOT / "Dataset502_ChestCTV"
GTV_DIR = NNUNET_ROOT / "Dataset503_ChestGTV"
MANIFEST = NNUNET_ROOT / "nnunet_export_manifest.csv"
OUT_DIR = ROOT / "outputs" / "gtv_ctv_target_visualization"


COLORS = {
    "ctv_only": np.array([31, 157, 255], dtype=np.float32) / 255.0,
    "overlap": np.array([255, 212, 71], dtype=np.float32) / 255.0,
    "gtv_only": np.array([255, 48, 80], dtype=np.float32) / 255.0,
    "ctv_line": "#1f9dff",
    "gtv_line": "#ff3050",
}


def nii_cases(dataset_dir: Path) -> set[str]:
    return {p.name[:-7] for p in (dataset_dir / "labelsTr").glob("*.nii.gz")}


def read_manifest() -> dict[tuple[str, str], dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    if not MANIFEST.exists():
        return rows
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            case_id = row.get("case_id", "")
            task = row.get("task", "")
            if case_id and task:
                rows[(case_id, task)] = row
    return rows


def load_case(case_id: str):
    image_path = CTV_DIR / "imagesTr" / f"{case_id}_0000.nii.gz"
    ctv_path = CTV_DIR / "labelsTr" / f"{case_id}.nii.gz"
    gtv_path = GTV_DIR / "labelsTr" / f"{case_id}.nii.gz"
    image = nib.load(str(image_path))
    ctv = nib.load(str(ctv_path))
    gtv = nib.load(str(gtv_path))
    if ctv.shape != gtv.shape or ctv.shape != image.shape:
        raise ValueError(f"Shape mismatch for {case_id}: image={image.shape}, CTV={ctv.shape}, GTV={gtv.shape}")
    if not np.allclose(ctv.affine, gtv.affine, atol=1e-4):
        raise ValueError(f"CTV/GTV affine mismatch for {case_id}")
    image_data = np.asanyarray(image.dataobj).astype(np.float32)
    ctv_mask = np.asanyarray(ctv.dataobj) > 0
    gtv_mask = np.asanyarray(gtv.dataobj) > 0
    return image, image_data, ctv_mask, gtv_mask


def voxel_volume_cm3(img) -> float:
    affine = img.affine
    spacing = [float(np.linalg.norm(affine[:3, i])) for i in range(3)]
    return float(np.prod(spacing) / 1000.0)


def window_ct(slice_2d: np.ndarray, low: float = -1000.0, high: float = 700.0) -> np.ndarray:
    arr = np.clip(slice_2d.astype(np.float32), low, high)
    return (arr - low) / (high - low)


def best_difference_slice(ctv: np.ndarray, gtv: np.ndarray) -> int:
    best_z = 0
    best_score = -1.0
    for z in range(ctv.shape[2]):
        ctv_z = ctv[:, :, z]
        gtv_z = gtv[:, :, z]
        if not np.any(ctv_z) and not np.any(gtv_z):
            continue
        overlap = np.count_nonzero(ctv_z & gtv_z)
        ctv_only = np.count_nonzero(ctv_z & ~gtv_z)
        gtv_only = np.count_nonzero(gtv_z & ~ctv_z)
        both_bonus = 1_000_000 if np.any(ctv_z) and np.any(gtv_z) else 0
        score = both_bonus + 40 * gtv_only + 4 * ctv_only + overlap
        if score > best_score:
            best_score = float(score)
            best_z = z
    return best_z


def orient(slice_2d: np.ndarray) -> np.ndarray:
    return np.rot90(slice_2d)


def blend(base: np.ndarray, mask: np.ndarray, color: np.ndarray, alpha: float) -> np.ndarray:
    out = base.copy()
    if np.any(mask):
        out[mask] = (1.0 - alpha) * out[mask] + alpha * color
    return out


def draw_mask_contours(ax, mask: np.ndarray, color: str, linewidth: float) -> None:
    if not np.any(mask):
        return
    for contour in measure.find_contours(mask.astype(float), 0.5):
        ax.plot(contour[:, 1], contour[:, 0], color=color, linewidth=linewidth)


def make_case_figure(case_id: str, image_data: np.ndarray, ctv: np.ndarray, gtv: np.ndarray, z: int, stats: dict) -> Path:
    ct_slice = orient(window_ct(image_data[:, :, z]))
    ctv_slice = orient(ctv[:, :, z])
    gtv_slice = orient(gtv[:, :, z])
    ctv_only = ctv_slice & ~gtv_slice
    overlap = ctv_slice & gtv_slice
    gtv_only = gtv_slice & ~ctv_slice

    base_rgb = np.dstack([ct_slice, ct_slice, ct_slice])
    diff_rgb = blend(base_rgb, ctv_only, COLORS["ctv_only"], 0.50)
    diff_rgb = blend(diff_rgb, overlap, COLORS["overlap"], 0.62)
    diff_rgb = blend(diff_rgb, gtv_only, COLORS["gtv_only"], 0.72)

    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.6), dpi=180)
    panels = [
        ("CTV contour", ctv_slice, None),
        ("GTV contour", gtv_slice, None),
        ("Difference map", None, diff_rgb),
    ]
    for ax, (title, contour_mask, rgb) in zip(axes, panels):
        ax.imshow(rgb if rgb is not None else ct_slice, cmap=None if rgb is not None else "gray", interpolation="nearest")
        if title == "CTV contour":
            draw_mask_contours(ax, contour_mask, COLORS["ctv_line"], 2.0)
        elif title == "GTV contour":
            draw_mask_contours(ax, contour_mask, COLORS["gtv_line"], 2.0)
        else:
            draw_mask_contours(ax, ctv_slice, COLORS["ctv_line"], 1.6)
            draw_mask_contours(ax, gtv_slice, COLORS["gtv_line"], 1.6)
        ax.set_title(title, fontsize=10, color="#172033")
        ax.axis("off")

    fig.suptitle(
        (
            f"{case_id} | axial slice {z} | "
            f"CTV {stats['ctv_cm3']:.1f} cm3, GTV {stats['gtv_cm3']:.1f} cm3, "
            f"GTV outside CTV {stats['gtv_outside_ctv_cm3']:.2f} cm3"
        ),
        fontsize=10.5,
        color="#172033",
    )
    handles = [
        plt.Line2D([0], [0], color=COLORS["ctv_line"], lw=3, label="CTV contour / CTV-only fill"),
        plt.Line2D([0], [0], color=COLORS["gtv_line"], lw=3, label="GTV contour / GTV outside CTV fill"),
        plt.Line2D([0], [0], color="#ffd447", lw=6, label="CTV and GTV overlap"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8)
    fig.tight_layout(rect=[0.0, 0.08, 1.0, 0.94])
    out = OUT_DIR / "case_pngs" / f"{case_id}_gtv_ctv_difference.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    return out


def write_contact_sheet(records: list[dict], out_path: Path, max_cases: int | None = None, cols: int = 2) -> Path:
    selected = records[:max_cases] if max_cases else records
    if not selected:
        raise ValueError("No records for contact sheet")
    rows = int(np.ceil(len(selected) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 7.2, rows * 2.85), dpi=150)
    axes_arr = np.atleast_1d(axes).ravel()
    for ax, rec in zip(axes_arr, selected):
        img = mpimg.imread(rec["png_path"])
        ax.imshow(img)
        ax.set_title(
            (
                f"{rec['case_id']} | slice {rec['slice_index']} | "
                f"outside {rec['gtv_outside_ctv_percent']:.1f}%"
            ),
            fontsize=8.5,
            color="#172033",
        )
        ax.axis("off")
    for ax in axes_arr[len(selected) :]:
        ax.axis("off")
    fig.tight_layout(pad=0.8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)
    return out_path


def case_stats(case_id: str, img, ctv: np.ndarray, gtv: np.ndarray, manifest_rows: dict[tuple[str, str], dict[str, str]]) -> dict:
    vv = voxel_volume_cm3(img)
    overlap = ctv & gtv
    ctv_only = ctv & ~gtv
    gtv_only = gtv & ~ctv
    ctv_vox = int(np.count_nonzero(ctv))
    gtv_vox = int(np.count_nonzero(gtv))
    overlap_vox = int(np.count_nonzero(overlap))
    ctv_only_vox = int(np.count_nonzero(ctv_only))
    gtv_only_vox = int(np.count_nonzero(gtv_only))
    ctv_row = manifest_rows.get((case_id, "CTV"), {})
    gtv_row = manifest_rows.get((case_id, "GTV"), {})
    return {
        "case_id": case_id,
        "patient_id": ctv_row.get("patient_id", ""),
        "scan_date": ctv_row.get("scan_date", ""),
        "scan_time": ctv_row.get("scan_time", ""),
        "ct_series_uid": ctv_row.get("ct_series_uid", ""),
        "ctv_roi_names": ctv_row.get("matched_rois", ""),
        "gtv_roi_names": gtv_row.get("matched_rois", ""),
        "ctv_voxels": ctv_vox,
        "gtv_voxels": gtv_vox,
        "overlap_voxels": overlap_vox,
        "ctv_only_voxels": ctv_only_vox,
        "gtv_outside_ctv_voxels": gtv_only_vox,
        "ctv_cm3": ctv_vox * vv,
        "gtv_cm3": gtv_vox * vv,
        "overlap_cm3": overlap_vox * vv,
        "ctv_only_cm3": ctv_only_vox * vv,
        "gtv_outside_ctv_cm3": gtv_only_vox * vv,
        "overlap_over_gtv_percent": (100.0 * overlap_vox / gtv_vox) if gtv_vox else 0.0,
        "gtv_outside_ctv_percent": (100.0 * gtv_only_vox / gtv_vox) if gtv_vox else 0.0,
        "ctv_only_over_ctv_percent": (100.0 * ctv_only_vox / ctv_vox) if ctv_vox else 0.0,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    both_cases = sorted(nii_cases(CTV_DIR) & nii_cases(GTV_DIR))
    manifest_rows = read_manifest()
    records: list[dict] = []

    for index, case_id in enumerate(both_cases, 1):
        img, image_data, ctv, gtv = load_case(case_id)
        stats = case_stats(case_id, img, ctv, gtv, manifest_rows)
        z = best_difference_slice(ctv, gtv)
        stats["slice_index"] = z
        png = make_case_figure(case_id, image_data, ctv, gtv, z, stats)
        stats["png_path"] = str(png)
        records.append(stats)
        print(f"[{index}/{len(both_cases)}] {case_id} slice={z} outside={stats['gtv_outside_ctv_percent']:.2f}%", flush=True)

    records.sort(
        key=lambda r: (
            float(r["gtv_outside_ctv_percent"]),
            float(r["gtv_outside_ctv_cm3"]),
            float(r["ctv_only_cm3"]),
        ),
        reverse=True,
    )

    write_csv(OUT_DIR / "gtv_ctv_both_cases_stats.csv", records)
    write_contact_sheet(records, OUT_DIR / "selected_gtv_ctv_difference_contact_sheet.png", max_cases=min(12, len(records)), cols=2)
    write_contact_sheet(records, OUT_DIR / "all_gtv_ctv_difference_contact_sheet.png", max_cases=None, cols=2)

    summary = {
        "ctv_cases": len(nii_cases(CTV_DIR)),
        "gtv_cases": len(nii_cases(GTV_DIR)),
        "both_ctv_gtv_cases": len(both_cases),
        "output_dir": str(OUT_DIR),
        "stats_csv": str(OUT_DIR / "gtv_ctv_both_cases_stats.csv"),
        "selected_contact_sheet": str(OUT_DIR / "selected_gtv_ctv_difference_contact_sheet.png"),
        "all_contact_sheet": str(OUT_DIR / "all_gtv_ctv_difference_contact_sheet.png"),
        "top_cases_by_gtv_outside_ctv": [
            {
                "case_id": r["case_id"],
                "slice_index": r["slice_index"],
                "gtv_outside_ctv_percent": r["gtv_outside_ctv_percent"],
                "gtv_outside_ctv_cm3": r["gtv_outside_ctv_cm3"],
                "png_path": r["png_path"],
            }
            for r in records[:12]
        ],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
