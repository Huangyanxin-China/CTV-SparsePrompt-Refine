from __future__ import annotations

import argparse
import csv
import json
import shutil
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom

from export_gtv_rtstruct_masks import (
    ROOT,
    as_text,
    build_geometry,
    choose_ct_series,
    match_categories,
    rasterize_roi,
    read_ct_headers,
    referenced_image_uids,
    roi_number_to_name,
    save_mask,
    structure_frame_uid,
    unique_gtv_structure_rows,
)


DEFAULT_INPUT_CSV = ROOT / "gtv_cases.csv"
DEFAULT_OUTPUT_DIR = ROOT / "nnUNet_raw_GTV_CTV_Organ"
DEFAULT_SOURCE = "all-rtstructs"

TASKS = {
    "Organ": {
        "dataset_id": 501,
        "dataset_name": "ChestOrgan",
        "labels": {"background": 0, "Lung": 1, "Heart": 2, "SpinalCord": 3, "Esophagus": 4},
        "categories": ["Lung", "Heart", "SpinalCord", "Esophagus"],
    },
    "CTV": {
        "dataset_id": 502,
        "dataset_name": "ChestCTV",
        "labels": {"background": 0, "CTV": 1},
        "categories": ["CTV"],
    },
    "GTV": {
        "dataset_id": 503,
        "dataset_name": "ChestGTV",
        "labels": {"background": 0, "GTV": 1},
        "categories": ["GTV"],
    },
}

TASK_ORDER = ["Organ", "CTV", "GTV"]


@dataclass
class ScanGroup:
    patient: str
    patient_id: str
    batch: str
    scan_date: str
    scan_time: str
    series_uid: str
    ct_headers: list[dict]
    geometry: dict
    rows: list[dict[str, str]] = field(default_factory=list)
    case_base: str = ""


def clean_patient_id(patient: str) -> str:
    return patient.removeprefix("patient_")


def patient_from_structure_path(path: Path) -> tuple[str, str]:
    parts = path.relative_to(ROOT).parts
    batch = parts[0] if parts else ""
    patient = ""
    for part in parts:
        if part.startswith("patient_"):
            patient = part
            break
    return batch, patient


def skip_dicom_candidate(path: Path) -> bool:
    skip_prefixes = ("nnUNet_raw", "nifti_labels")
    for part in path.relative_to(ROOT).parts:
        if part == "__pycache__" or part.startswith(skip_prefixes):
            return True
    return False


def iter_rt_dicom_candidates() -> list[Path]:
    candidates: list[Path] = []
    for batch_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        if batch_dir.name == "__pycache__" or batch_dir.name.startswith(("nnUNet_raw", "nifti_labels")):
            continue
        patient_dirs = sorted(p for p in batch_dir.iterdir() if p.is_dir() and p.name.startswith("patient_"))
        for patient_dir in patient_dirs:
            for dicom_dir_name in ("CT_SET", "DICOM_PLAN"):
                dicom_dir = patient_dir / dicom_dir_name
                if dicom_dir.is_dir():
                    candidates.extend(sorted(dicom_dir.glob("*.DCM")))
                    candidates.extend(sorted(dicom_dir.glob("*.dcm")))
    return candidates


def all_rtstruct_rows(limit: int = 0) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[Path] = set()
    candidates = iter_rt_dicom_candidates()

    for idx, path in enumerate(candidates, 1):
        if path in seen or skip_dicom_candidate(path):
            continue
        seen.add(path)
        try:
            ds = pydicom.dcmread(
                str(path),
                force=True,
                stop_before_pixels=True,
                specific_tags=["Modality", "SOPInstanceUID"],
            )
        except Exception:
            continue
        if as_text(getattr(ds, "Modality", "")).strip() != "RTSTRUCT":
            continue

        batch, patient = patient_from_structure_path(path)
        rows.append(
            {
                "batch": batch,
                "patient": patient,
                "structure_file": str(path),
                "structure_uid": as_text(getattr(ds, "SOPInstanceUID", "")).strip(),
            }
        )
        if idx % 5000 == 0:
            print(f"scanned {idx}/{len(candidates)} DICOM candidates, RTSTRUCT rows={len(rows)}...", flush=True)
        if limit and len(rows) >= limit:
            break

    rows.sort(key=lambda r: (r.get("batch", ""), r.get("patient", ""), r.get("structure_file", "")))
    return rows


def dicom_date_time(ct_headers: list[dict]) -> tuple[str, str]:
    first_path = ct_headers[0]["path"]
    tags = [
        "AcquisitionDate",
        "SeriesDate",
        "StudyDate",
        "ContentDate",
        "AcquisitionTime",
        "SeriesTime",
        "StudyTime",
        "ContentTime",
    ]
    ds = pydicom.dcmread(str(first_path), force=True, stop_before_pixels=True, specific_tags=tags)
    date = (
        str(getattr(ds, "AcquisitionDate", "") or "")
        or str(getattr(ds, "SeriesDate", "") or "")
        or str(getattr(ds, "StudyDate", "") or "")
        or str(getattr(ds, "ContentDate", "") or "")
    )
    time = (
        str(getattr(ds, "AcquisitionTime", "") or "")
        or str(getattr(ds, "SeriesTime", "") or "")
        or str(getattr(ds, "StudyTime", "") or "")
        or str(getattr(ds, "ContentTime", "") or "")
    )
    date = "".join(ch for ch in date if ch.isdigit())[:8] or "unknownDate"
    time = "".join(ch for ch in time if ch.isdigit())[:6]
    return date, time


def sorted_ct_headers(ct_headers: list[dict]) -> list[dict]:
    first = ct_headers[0]
    row_cos = first["iop"][:3]
    col_cos = first["iop"][3:]
    normal = np.cross(row_cos, col_cos)
    normal = normal / np.linalg.norm(normal)
    for header in ct_headers:
        header["slice_pos"] = float(np.dot(normal, header["ipp"]))
    return sorted(ct_headers, key=lambda h: h["slice_pos"])


def load_ct_volume(ct_headers: list[dict]) -> np.ndarray:
    slices = []
    for header in sorted_ct_headers(ct_headers):
        ds = pydicom.dcmread(str(header["path"]), force=True)
        arr = ds.pixel_array.astype(np.float32)
        slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
        intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)
        arr = arr * slope + intercept
        slices.append(arr)

    volume = np.stack(slices, axis=0)
    if np.nanmin(volume) >= np.iinfo(np.int16).min and np.nanmax(volume) <= np.iinfo(np.int16).max:
        rounded = np.rint(volume)
        if np.allclose(volume, rounded, atol=1e-3):
            return rounded.astype(np.int16)
    return volume.astype(np.float32)


def save_image(volume_zyx: np.ndarray, affine_ras: np.ndarray, path: Path) -> None:
    data_xyz = np.transpose(volume_zyx, (2, 1, 0))
    img = nib.Nifti1Image(data_xyz, affine_ras)
    img.header.set_xyzt_units("mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(img, str(path))


def scan_group_key(row: dict[str, str]) -> tuple[str, str]:
    return (clean_patient_id(row["patient"]), row["ct_series_uid"])


def collect_scan_groups(rows: list[dict[str, str]]) -> list[ScanGroup]:
    groups: dict[tuple[str, str], ScanGroup] = {}

    for idx, row in enumerate(rows, 1):
        structure_path = Path(row["structure_file"])
        rtstruct = pydicom.dcmread(str(structure_path), force=True, stop_before_pixels=True)
        ct_dir = structure_path.parent
        ct_headers = choose_ct_series(
            read_ct_headers(ct_dir),
            structure_frame_uid(rtstruct),
            referenced_image_uids(rtstruct),
        )
        geometry = build_geometry(ct_headers)
        row["ct_series_uid"] = geometry["series_uid"]
        key = scan_group_key(row)

        if key not in groups:
            scan_date, scan_time = dicom_date_time(ct_headers)
            groups[key] = ScanGroup(
                patient=row["patient"],
                patient_id=clean_patient_id(row["patient"]),
                batch=row["batch"],
                scan_date=scan_date,
                scan_time=scan_time,
                series_uid=geometry["series_uid"],
                ct_headers=ct_headers,
                geometry=geometry,
            )
        groups[key].rows.append(row)

        if idx % 25 == 0:
            print(f"collected {idx}/{len(rows)} RTSTRUCT rows...", flush=True)

    assign_case_names(list(groups.values()))
    return sorted(groups.values(), key=lambda g: (g.patient_id, g.scan_date, g.scan_time, g.series_uid))


def assign_case_names(groups: list[ScanGroup]) -> None:
    by_patient_date: dict[tuple[str, str], list[ScanGroup]] = defaultdict(list)
    for group in groups:
        by_patient_date[(group.patient_id, group.scan_date)].append(group)

    provisional_counts: dict[str, int] = defaultdict(int)
    for group in groups:
        same_day = by_patient_date[(group.patient_id, group.scan_date)]
        stamp = group.scan_date
        if len(same_day) > 1 and group.scan_time:
            stamp = f"{group.scan_date}{group.scan_time}"
        base = f"{group.patient_id}_{stamp}"
        provisional_counts[base] += 1
        if provisional_counts[base] > 1:
            base = f"{base}_{provisional_counts[base]}"
        group.case_base = base


def empty_masks(geometry: dict) -> dict[str, np.ndarray]:
    shape = (geometry["slices"], geometry["rows"], geometry["cols"])
    return {
        "GTV": np.zeros(shape, dtype=bool),
        "CTV": np.zeros(shape, dtype=bool),
        "Lung": np.zeros(shape, dtype=bool),
        "Heart": np.zeros(shape, dtype=bool),
        "SpinalCord": np.zeros(shape, dtype=bool),
        "Esophagus": np.zeros(shape, dtype=bool),
    }


def build_group_masks(group: ScanGroup) -> tuple[dict[str, np.ndarray], dict[str, list[str]]]:
    masks = empty_masks(group.geometry)
    matched_names: dict[str, list[str]] = {category: [] for category in masks}

    for row in group.rows:
        rtstruct = pydicom.dcmread(row["structure_file"], force=True, stop_before_pixels=True)
        matches = match_categories(roi_number_to_name(rtstruct))
        for category, items in matches.items():
            for roi_number, roi_name in items:
                roi_mask = rasterize_roi(rtstruct, roi_number, group.geometry)
                if roi_mask.any():
                    masks[category] |= roi_mask
                    if roi_name not in matched_names[category]:
                        matched_names[category].append(roi_name)

    return masks, matched_names


def organ_label(masks: dict[str, np.ndarray]) -> np.ndarray:
    label = np.zeros_like(masks["Lung"], dtype=np.uint8)
    label[masks["Lung"]] = 1
    label[masks["Heart"]] = 2
    label[masks["SpinalCord"]] = 3
    label[masks["Esophagus"]] = 4
    return label


def task_dir(output_dir: Path, task: str) -> Path:
    cfg = TASKS[task]
    return output_dir / f"Dataset{cfg['dataset_id']:03d}_{cfg['dataset_name']}"


def write_dataset_json(dataset_dir: Path, task: str, num_training: int) -> None:
    cfg = TASKS[task]
    payload = {
        "channel_names": {"0": "CT"},
        "labels": cfg["labels"],
        "numTraining": num_training,
        "file_ending": ".nii.gz",
    }
    (dataset_dir / "dataset.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def prepare_dirs(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise RuntimeError(f"Output directory already exists: {output_dir}")
        resolved = output_dir.resolve()
        root = ROOT.resolve()
        if root not in resolved.parents and resolved != root:
            raise RuntimeError(f"Refusing to remove path outside workspace: {resolved}")
        if not output_dir.name.startswith("nnUNet_raw"):
            raise RuntimeError(f"Refusing to remove unexpected output directory: {resolved}")
        shutil.rmtree(output_dir)

    for task in TASK_ORDER:
        dataset_dir = task_dir(output_dir, task)
        (dataset_dir / "imagesTr").mkdir(parents=True, exist_ok=True)
        (dataset_dir / "labelsTr").mkdir(parents=True, exist_ok=True)


def export_group(group: ScanGroup, output_dir: Path) -> list[dict[str, str]]:
    masks, matched_names = build_group_masks(group)
    image = load_ct_volume(group.ct_headers)
    manifest_rows: list[dict[str, str]] = []

    task_labels = {
        "Organ": organ_label(masks),
        "CTV": masks["CTV"].astype(np.uint8),
        "GTV": masks["GTV"].astype(np.uint8),
    }

    for task in TASK_ORDER:
        label = task_labels[task]
        voxel_count = int(np.count_nonzero(label))
        case_id = group.case_base
        dataset_dir = task_dir(output_dir, task)
        image_file = dataset_dir / "imagesTr" / f"{case_id}_0000.nii.gz"
        label_file = dataset_dir / "labelsTr" / f"{case_id}.nii.gz"

        if voxel_count > 0:
            save_image(image, group.geometry["affine_ras"], image_file)
            save_mask(label, group.geometry["affine_ras"], label_file)
            status = "written"
        else:
            status = "missing_label"

        categories = TASKS[task]["categories"]
        names = []
        for category in categories:
            names.extend(matched_names.get(category, []))

        manifest_rows.append(
            {
                "task": task,
                "case_id": case_id,
                "patient": group.patient,
                "patient_id": group.patient_id,
                "scan_date": group.scan_date,
                "scan_time": group.scan_time,
                "ct_series_uid": group.series_uid,
                "rtstruct_count": str(len(group.rows)),
                "matched_rois": "; ".join(names),
                "voxel_count": str(voxel_count),
                "image_file": str(image_file) if voxel_count > 0 else "",
                "label_file": str(label_file) if voxel_count > 0 else "",
                "status": status,
            }
        )

    return manifest_rows


def write_manifest(output_dir: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "task",
        "case_id",
        "patient",
        "patient_id",
        "scan_date",
        "scan_time",
        "ct_series_uid",
        "rtstruct_count",
        "matched_rois",
        "voxel_count",
        "image_file",
        "label_file",
        "status",
    ]
    with (output_dir / "nnunet_export_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare nnUNet datasets for Organ, CTV, and GTV labels.")
    parser.add_argument(
        "--source",
        choices=["all-rtstructs", "gtv-cases", "input-csv"],
        default=DEFAULT_SOURCE,
        help="RTSTRUCT source. Default scans every .DCM RTSTRUCT under the workspace.",
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    warnings.filterwarnings("ignore", category=UserWarning, module="pydicom")
    if args.source == "all-rtstructs":
        rows = all_rtstruct_rows(args.limit)
    else:
        rows = unique_gtv_structure_rows(args.input_csv)
    if args.limit and args.source != "all-rtstructs":
        rows = rows[: args.limit]

    print(f"Source: {args.source}")
    print(f"RTSTRUCT rows: {len(rows)}")
    groups = collect_scan_groups(rows)
    print(f"Unique CT scans: {len(groups)}")

    prepare_dirs(args.output_dir, args.overwrite)
    manifest_rows: list[dict[str, str]] = []

    for idx, group in enumerate(groups, 1):
        print(f"[{idx}/{len(groups)}] exporting {group.case_base}", flush=True)
        try:
            manifest_rows.extend(export_group(group, args.output_dir))
        except Exception as exc:
            for task in TASK_ORDER:
                manifest_rows.append(
                    {
                        "task": task,
                        "case_id": group.case_base,
                        "patient": group.patient,
                        "patient_id": group.patient_id,
                        "scan_date": group.scan_date,
                        "scan_time": group.scan_time,
                        "ct_series_uid": group.series_uid,
                        "rtstruct_count": str(len(group.rows)),
                        "matched_rois": "",
                        "voxel_count": "",
                        "image_file": "",
                        "label_file": "",
                        "status": f"error: {exc}",
                    }
                )
            print(f"  ERROR: {exc}", flush=True)

    write_manifest(args.output_dir, manifest_rows)
    for task in TASK_ORDER:
        written = [row for row in manifest_rows if row["task"] == task and row["status"] == "written"]
        write_dataset_json(task_dir(args.output_dir, task), task, len(written))
        print(f"{task}: {len(written)} training cases")

    print(f"Output: {args.output_dir}")
    print(f"Manifest: {args.output_dir / 'nnunet_export_manifest.csv'}")


if __name__ == "__main__":
    main()
