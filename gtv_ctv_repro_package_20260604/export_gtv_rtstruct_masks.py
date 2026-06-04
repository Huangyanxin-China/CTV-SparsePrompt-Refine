from __future__ import annotations

import argparse
import csv
import json
import re
import warnings
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
from skimage.draw import polygon


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_CSV = ROOT / "gtv_cases.csv"
DEFAULT_OUTPUT_DIR = ROOT / "nifti_labels_gtv"

LPS_TO_RAS = np.diag([-1.0, -1.0, 1.0, 1.0])

CATEGORY_RULES = {
    "GTV": {
        "label": 1,
        "patterns": [r"gtv", r"\u5927\u4f53\u80bf\u7624", r"\u80bf\u7624\u9776\u533a"],
        "compact_keywords": ["gtv", "\u5927\u4f53\u80bf\u7624", "\u80bf\u7624\u9776\u533a"],
    },
    "CTV": {
        "label": 2,
        "patterns": [r"ctv", r"\u4e34\u5e8a\u9776\u533a"],
        "compact_keywords": ["ctv", "\u4e34\u5e8a\u9776\u533a"],
    },
    "Lung": {
        "label": 3,
        "patterns": [r"lung", r"pulmo", r"\u80ba"],
        "compact_keywords": ["lung", "pulmo", "\u80ba"],
    },
    "Heart": {
        "label": 4,
        "patterns": [r"heart", r"cardiac", r"pericard", r"\u5fc3"],
        "compact_keywords": ["heart", "cardiac", "pericard", "\u5fc3"],
    },
    "SpinalCord": {
        "label": 5,
        "patterns": [r"spinal", r"cord", r"myelon", r"\u810a\u9ad3"],
        "compact_keywords": ["spinalcord", "spinal", "cord", "myelon", "\u810a\u9ad3"],
    },
    "Esophagus": {
        "label": 6,
        "patterns": [r"esoph", r"oesoph", r"(^|[^a-z0-9])eso([^a-z0-9]|$)", r"\u98df\u7ba1"],
        "compact_keywords": ["esoph", "oesoph", "\u98df\u7ba1"],
    },
}

CATEGORY_PRIORITY = ["Lung", "Heart", "SpinalCord", "Esophagus", "CTV", "GTV"]
CT_HEADER_CACHE: dict[Path, list[dict]] = {}


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def safe_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unnamed"


def normalize_roi_name(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text).casefold()


def patient_from_path(path: Path) -> tuple[str, str]:
    parts = path.relative_to(ROOT).parts
    batch = parts[0] if len(parts) > 0 else ""
    patient = ""
    for part in parts:
        if part.startswith("patient_"):
            patient = part
            break
    return batch, patient


def unique_gtv_structure_rows(input_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            structure_file = row.get("structure_file", "").strip()
            if not structure_file or structure_file in seen:
                continue
            seen.add(structure_file)
            rows.append(row)
    rows.sort(key=lambda r: (r.get("batch", ""), r.get("patient", ""), r.get("structure_file", "")))
    return rows


def roi_number_to_name(rtstruct) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for item in getattr(rtstruct, "StructureSetROISequence", []) or []:
        try:
            number = int(item.ROINumber)
        except Exception:
            continue
        mapping[number] = as_text(getattr(item, "ROIName", "")).strip()
    return mapping


def match_categories(roi_names: dict[int, str]) -> dict[str, list[tuple[int, str]]]:
    matches: dict[str, list[tuple[int, str]]] = {category: [] for category in CATEGORY_RULES}
    for number, name in roi_names.items():
        folded = name.casefold()
        compact = normalize_roi_name(name)
        for category, rule in CATEGORY_RULES.items():
            pattern_match = any(re.search(pattern, folded, flags=re.IGNORECASE) for pattern in rule["patterns"])
            compact_match = any(keyword in compact for keyword in rule.get("compact_keywords", []))
            if pattern_match or compact_match:
                matches[category].append((number, name))
    return matches


def referenced_image_uids(rtstruct) -> set[str]:
    uids: set[str] = set()
    for roi_contour in getattr(rtstruct, "ROIContourSequence", []) or []:
        for contour in getattr(roi_contour, "ContourSequence", []) or []:
            for image in getattr(contour, "ContourImageSequence", []) or []:
                uid = as_text(getattr(image, "ReferencedSOPInstanceUID", "")).strip()
                if uid:
                    uids.add(uid)
    return uids


def structure_frame_uid(rtstruct) -> str:
    for item in getattr(rtstruct, "ReferencedFrameOfReferenceSequence", []) or []:
        uid = as_text(getattr(item, "FrameOfReferenceUID", "")).strip()
        if uid:
            return uid
    return as_text(getattr(rtstruct, "FrameOfReferenceUID", "")).strip()


def read_ct_headers(ct_dir: Path) -> list[dict]:
    cache_key = ct_dir.resolve()
    if cache_key in CT_HEADER_CACHE:
        return CT_HEADER_CACHE[cache_key]

    tags = [
        "Modality",
        "SOPInstanceUID",
        "SeriesInstanceUID",
        "FrameOfReferenceUID",
        "ImagePositionPatient",
        "ImageOrientationPatient",
        "PixelSpacing",
        "Rows",
        "Columns",
        "SliceThickness",
        "SpacingBetweenSlices",
    ]
    headers: list[dict] = []
    for path in ct_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            ds = pydicom.dcmread(
                str(path),
                force=True,
                stop_before_pixels=True,
                specific_tags=tags,
            )
        except Exception:
            continue
        if as_text(getattr(ds, "Modality", "")).strip() != "CT":
            continue
        required = ["SOPInstanceUID", "ImagePositionPatient", "ImageOrientationPatient", "PixelSpacing", "Rows", "Columns"]
        if any(not hasattr(ds, attr) for attr in required):
            continue
        headers.append(
            {
                "path": path,
                "sop_uid": as_text(ds.SOPInstanceUID).strip(),
                "series_uid": as_text(getattr(ds, "SeriesInstanceUID", "")).strip(),
                "frame_uid": as_text(getattr(ds, "FrameOfReferenceUID", "")).strip(),
                "ipp": np.asarray(ds.ImagePositionPatient, dtype=float),
                "iop": np.asarray(ds.ImageOrientationPatient, dtype=float),
                "pixel_spacing": np.asarray(ds.PixelSpacing, dtype=float),
                "rows": int(ds.Rows),
                "cols": int(ds.Columns),
                "slice_thickness": float(getattr(ds, "SliceThickness", 1.0) or 1.0),
                "spacing_between_slices": float(getattr(ds, "SpacingBetweenSlices", 0.0) or 0.0),
            }
        )
    CT_HEADER_CACHE[cache_key] = headers
    return headers


def choose_ct_series(headers: list[dict], frame_uid: str, referenced_uids: set[str]) -> list[dict]:
    if frame_uid:
        framed = [h for h in headers if h["frame_uid"] == frame_uid]
        if framed:
            headers = framed

    by_series: dict[str, list[dict]] = {}
    for h in headers:
        by_series.setdefault(h["series_uid"], []).append(h)

    if not by_series:
        raise RuntimeError("No CT series found in CT_SET")

    def score(series_headers: list[dict]) -> tuple[int, int]:
        uids = {h["sop_uid"] for h in series_headers}
        return (len(uids & referenced_uids), len(series_headers))

    return max(by_series.values(), key=score)


def build_geometry(ct_headers: list[dict]) -> dict:
    first = ct_headers[0]
    rows = first["rows"]
    cols = first["cols"]
    row_cos = first["iop"][:3]
    col_cos = first["iop"][3:]
    normal = np.cross(row_cos, col_cos)
    normal = normal / np.linalg.norm(normal)

    for h in ct_headers:
        h["slice_pos"] = float(np.dot(normal, h["ipp"]))

    ct_headers = sorted(ct_headers, key=lambda h: h["slice_pos"])
    positions = np.asarray([h["ipp"] for h in ct_headers], dtype=float)
    slice_positions = np.asarray([h["slice_pos"] for h in ct_headers], dtype=float)
    diffs = np.diff(slice_positions)
    slice_spacing = float(np.median(np.abs(diffs))) if len(diffs) else first["slice_thickness"]
    if slice_spacing <= 0:
        slice_spacing = first["slice_thickness"] or 1.0

    row_spacing = float(first["pixel_spacing"][0])
    col_spacing = float(first["pixel_spacing"][1])

    affine_lps = np.eye(4, dtype=float)
    affine_lps[:3, 0] = row_cos * col_spacing
    affine_lps[:3, 1] = col_cos * row_spacing
    affine_lps[:3, 2] = normal * slice_spacing
    affine_lps[:3, 3] = positions[0]

    return {
        "rows": rows,
        "cols": cols,
        "slices": len(ct_headers),
        "row_cos": row_cos,
        "col_cos": col_cos,
        "normal": normal,
        "row_spacing": row_spacing,
        "col_spacing": col_spacing,
        "positions": positions,
        "slice_positions": slice_positions,
        "uid_to_slice": {h["sop_uid"]: i for i, h in enumerate(ct_headers)},
        "series_uid": first["series_uid"],
        "affine_ras": LPS_TO_RAS @ affine_lps,
    }


def find_roi_contour(rtstruct, roi_number: int):
    for item in getattr(rtstruct, "ROIContourSequence", []) or []:
        try:
            if int(getattr(item, "ReferencedROINumber", -1)) == int(roi_number):
                return item
        except Exception:
            continue
    return None


def contour_slice_index(contour, points: np.ndarray, geometry: dict) -> int:
    for image in getattr(contour, "ContourImageSequence", []) or []:
        uid = as_text(getattr(image, "ReferencedSOPInstanceUID", "")).strip()
        if uid in geometry["uid_to_slice"]:
            return geometry["uid_to_slice"][uid]

    pos = float(np.median(points @ geometry["normal"]))
    return int(np.argmin(np.abs(geometry["slice_positions"] - pos)))


def rasterize_roi(rtstruct, roi_number: int, geometry: dict) -> np.ndarray:
    mask = np.zeros((geometry["slices"], geometry["rows"], geometry["cols"]), dtype=bool)
    roi_contour = find_roi_contour(rtstruct, roi_number)
    if roi_contour is None:
        return mask

    for contour in getattr(roi_contour, "ContourSequence", []) or []:
        contour_type = as_text(getattr(contour, "ContourGeometricType", "")).strip().upper()
        if contour_type and "CLOSED" not in contour_type:
            continue
        data = getattr(contour, "ContourData", None)
        if data is None or len(data) < 9:
            continue
        points = np.asarray(data, dtype=float).reshape(-1, 3)
        slice_idx = contour_slice_index(contour, points, geometry)
        if slice_idx < 0 or slice_idx >= geometry["slices"]:
            continue

        origin = geometry["positions"][slice_idx]
        delta = points - origin
        cols = delta @ geometry["row_cos"] / geometry["col_spacing"]
        rows = delta @ geometry["col_cos"] / geometry["row_spacing"]
        rr, cc = polygon(rows, cols, shape=(geometry["rows"], geometry["cols"]))
        mask[slice_idx, rr, cc] = True

    return mask


def save_mask(mask_zyx: np.ndarray, affine_ras: np.ndarray, path: Path) -> None:
    data_xyz = np.transpose(mask_zyx.astype(np.uint8), (2, 1, 0))
    img = nib.Nifti1Image(data_xyz, affine_ras)
    img.header.set_xyzt_units("mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(img, str(path))


def export_one(row: dict[str, str], output_dir: Path, write_empty: bool) -> list[dict[str, str]]:
    structure_path = Path(row["structure_file"])
    plan_path = Path(row.get("plan_file", ""))
    batch = row.get("batch") or patient_from_path(structure_path)[0]
    patient = row.get("patient") or patient_from_path(structure_path)[1]
    structure_uid = row.get("structure_uid") or structure_path.stem
    export_id = f"{safe_name(batch)}__{safe_name(patient)}__rtstruct_{safe_name(structure_uid[-12:])}"
    case_dir = output_dir / export_id

    rtstruct = pydicom.dcmread(str(structure_path), force=True, stop_before_pixels=True)
    roi_names = roi_number_to_name(rtstruct)
    category_matches = match_categories(roi_names)

    frame_uid = structure_frame_uid(rtstruct)
    ct_dir = structure_path.parent
    ct_headers = choose_ct_series(read_ct_headers(ct_dir), frame_uid, referenced_image_uids(rtstruct))
    geometry = build_geometry(ct_headers)

    manifest_rows: list[dict[str, str]] = []
    labelmap = np.zeros((geometry["slices"], geometry["rows"], geometry["cols"]), dtype=np.uint8)
    category_masks: dict[str, np.ndarray] = {}

    for category in CATEGORY_RULES:
        combined = np.zeros((geometry["slices"], geometry["rows"], geometry["cols"]), dtype=bool)
        matched_names: list[str] = []
        for roi_number, roi_name in category_matches[category]:
            roi_mask = rasterize_roi(rtstruct, roi_number, geometry)
            if roi_mask.any():
                combined |= roi_mask
                matched_names.append(roi_name)

        voxel_count = int(combined.sum())
        mask_file = ""
        status = "missing"
        if matched_names and (voxel_count > 0 or write_empty):
            mask_path = case_dir / f"mask_{category}.nii.gz"
            save_mask(combined, geometry["affine_ras"], mask_path)
            mask_file = str(mask_path)
            status = "written" if voxel_count > 0 else "empty_written"
            category_masks[category] = combined
        elif matched_names:
            status = "matched_no_voxels"

        manifest_rows.append(
            {
                "export_id": export_id,
                "batch": batch,
                "patient": patient,
                "structure_uid": structure_uid,
                "plan_file": str(plan_path),
                "structure_file": str(structure_path),
                "ct_series_uid": geometry["series_uid"],
                "ct_slices": str(geometry["slices"]),
                "category": category,
                "label_value": str(CATEGORY_RULES[category]["label"]),
                "matched_rois": "; ".join(matched_names),
                "voxel_count": str(voxel_count),
                "mask_file": mask_file,
                "status": status,
            }
        )

    for category in CATEGORY_PRIORITY:
        if category in category_masks:
            labelmap[category_masks[category]] = CATEGORY_RULES[category]["label"]

    if labelmap.any() or write_empty:
        save_mask(labelmap, geometry["affine_ras"], case_dir / "labelmap.nii.gz")
        label_info = {category: rule["label"] for category, rule in CATEGORY_RULES.items()}
        (case_dir / "label_values.json").write_text(json.dumps(label_info, indent=2), encoding="utf-8")
    return manifest_rows


def dry_run(rows: list[dict[str, str]]) -> None:
    totals = {category: 0 for category in CATEGORY_RULES}
    print(f"Unique RTSTRUCT files with GTV: {len(rows)}")
    for row in rows:
        rtstruct = pydicom.dcmread(row["structure_file"], force=True, stop_before_pixels=True)
        matches = match_categories(roi_number_to_name(rtstruct))
        parts = []
        for category, items in matches.items():
            names = [name for _, name in items]
            if names:
                totals[category] += 1
                parts.append(f"{category}=[{'; '.join(names)}]")
        if parts:
            print(f"{row.get('batch')}\\{row.get('patient')}: " + " | ".join(parts))
    print("Matched structure counts:")
    for category, count in totals.items():
        print(f"  {category}: {count}")


def write_manifest(rows: list[dict[str, str]], output_dir: Path) -> None:
    fieldnames = [
        "export_id",
        "batch",
        "patient",
        "structure_uid",
        "plan_file",
        "structure_file",
        "ct_series_uid",
        "ct_slices",
        "category",
        "label_value",
        "matched_rois",
        "voxel_count",
        "mask_file",
        "status",
    ]
    with (output_dir / "export_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_label_values(output_dir: Path) -> None:
    label_info = {category: rule["label"] for category, rule in CATEGORY_RULES.items()}
    (output_dir / "label_values.json").write_text(json.dumps(label_info, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export selected RTSTRUCT labels from GTV cases to NIfTI masks.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--write-empty", action="store_true")
    args = parser.parse_args()

    warnings.filterwarnings("ignore", category=UserWarning, module="pydicom")
    rows = unique_gtv_structure_rows(args.input_csv)
    if args.limit:
        rows = rows[: args.limit]

    if args.dry_run:
        dry_run(rows)
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_label_values(args.output_dir)
    all_manifest_rows: list[dict[str, str]] = []
    for idx, row in enumerate(rows, 1):
        print(f"[{idx}/{len(rows)}] exporting {row.get('batch')}\\{row.get('patient')}", flush=True)
        try:
            all_manifest_rows.extend(export_one(row, args.output_dir, args.write_empty))
        except Exception as exc:
            all_manifest_rows.append(
                {
                    "export_id": "",
                    "batch": row.get("batch", ""),
                    "patient": row.get("patient", ""),
                    "structure_uid": row.get("structure_uid", ""),
                    "plan_file": row.get("plan_file", ""),
                    "structure_file": row.get("structure_file", ""),
                    "ct_series_uid": "",
                    "ct_slices": "",
                    "category": "",
                    "label_value": "",
                    "matched_rois": "",
                    "voxel_count": "",
                    "mask_file": "",
                    "status": f"error: {exc}",
                }
            )
            print(f"  ERROR: {exc}", flush=True)

    write_manifest(all_manifest_rows, args.output_dir)
    written = sum(1 for r in all_manifest_rows if r["status"] == "written")
    errors = [r for r in all_manifest_rows if r["status"].startswith("error")]
    print(f"Done. Written masks: {written}")
    print(f"Errors: {len(errors)}")
    print(f"Output: {args.output_dir}")
    print(f"Manifest: {args.output_dir / 'export_manifest.csv'}")


if __name__ == "__main__":
    main()
