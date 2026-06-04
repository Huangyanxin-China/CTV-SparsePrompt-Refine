#!/usr/bin/env python
import argparse
import csv
import math
import os
from collections import defaultdict

import numpy as np
import SimpleITK as sitk


TAG_NAMES = {
    "0008|0016": "sop_class_uid",
    "0008|0020": "study_date",
    "0008|0030": "study_time",
    "0008|0060": "modality",
    "0008|0070": "manufacturer",
    "0008|1030": "study_description",
    "0008|103e": "series_description",
    "0010|0010": "patient_name",
    "0010|0020": "patient_id",
    "0018|0015": "body_part_examined",
    "0018|0050": "slice_thickness",
    "0018|0060": "kvp",
    "0018|0088": "spacing_between_slices",
    "0018|1100": "reconstruction_diameter",
    "0018|1210": "convolution_kernel",
    "0020|000d": "study_instance_uid",
    "0020|000e": "series_instance_uid",
    "0020|0032": "image_position_patient",
    "0020|0037": "image_orientation_patient",
    "0020|1041": "slice_location",
    "0028|0010": "rows",
    "0028|0011": "columns",
    "0028|0030": "pixel_spacing",
    "0028|1052": "rescale_intercept",
    "0028|1053": "rescale_slope",
}


def clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    return " ".join(text.split())


def split_dicom_float_list(value):
    if value is None:
        return []
    parts = str(value).replace(",", "\\").split("\\")
    out = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            return []
    return out


def parse_float(value):
    try:
        return float(str(value).strip())
    except Exception:
        return math.nan


def parse_int(value):
    try:
        return int(float(str(value).strip()))
    except Exception:
        return 0


def read_file_metadata(path):
    reader = sitk.ImageFileReader()
    reader.SetFileName(path)
    reader.LoadPrivateTagsOn()
    reader.ReadImageInformation()
    meta = {}
    for tag, name in TAG_NAMES.items():
        meta[name] = clean_text(reader.GetMetaData(tag)) if reader.HasMetaDataKey(tag) else ""
    return meta


def orientation_normal(iop):
    vals = split_dicom_float_list(iop)
    if len(vals) != 6:
        return None
    row = np.asarray(vals[:3], dtype=np.float64)
    col = np.asarray(vals[3:], dtype=np.float64)
    normal = np.cross(row, col)
    norm = np.linalg.norm(normal)
    if norm <= 0:
        return None
    return normal / norm


def position_along_normal(ipp, normal):
    vals = split_dicom_float_list(ipp)
    if len(vals) != 3 or normal is None:
        return math.nan
    return float(np.dot(np.asarray(vals, dtype=np.float64), normal))


def summarize_positions(files, first_meta):
    normal = orientation_normal(first_meta.get("image_orientation_patient", ""))
    positions = []
    instance_locations = []
    failed = 0
    for path in files:
        try:
            meta = read_file_metadata(path)
        except Exception:
            failed += 1
            continue
        pos = position_along_normal(meta.get("image_position_patient", ""), normal)
        if not math.isnan(pos):
            positions.append(pos)
        loc = parse_float(meta.get("slice_location", ""))
        if not math.isnan(loc):
            instance_locations.append(loc)

    source = "image_position_patient"
    values = positions
    if len(values) < 2 and len(instance_locations) >= 2:
        source = "slice_location"
        values = instance_locations

    if len(values) < 2:
        return {
            "slice_position_source": source if values else "",
            "slice_position_count": len(values),
            "metadata_read_failures": failed,
            "z_spacing_median": "",
            "z_spacing_min": "",
            "z_spacing_max": "",
            "z_spacing_std": "",
            "z_extent_mm": "",
            "z_nonuniform": "",
        }

    arr = np.sort(np.asarray(values, dtype=np.float64))
    diffs = np.abs(np.diff(arr))
    diffs = diffs[diffs > 1e-4]
    if diffs.size == 0:
        return {
            "slice_position_source": source,
            "slice_position_count": len(values),
            "metadata_read_failures": failed,
            "z_spacing_median": "",
            "z_spacing_min": "",
            "z_spacing_max": "",
            "z_spacing_std": "",
            "z_extent_mm": float(arr.max() - arr.min()),
            "z_nonuniform": "",
        }
    z_min = float(np.min(diffs))
    z_max = float(np.max(diffs))
    return {
        "slice_position_source": source,
        "slice_position_count": len(values),
        "metadata_read_failures": failed,
        "z_spacing_median": float(np.median(diffs)),
        "z_spacing_min": z_min,
        "z_spacing_max": z_max,
        "z_spacing_std": float(np.std(diffs)),
        "z_extent_mm": float(arr.max() - arr.min()),
        "z_nonuniform": int((z_max - z_min) > 0.05),
    }


def series_row(root, directory, series_id, files, args):
    first_file = files[0]
    meta = read_file_metadata(first_file)
    rows = parse_int(meta.get("rows"))
    columns = parse_int(meta.get("columns"))
    pixel_spacing = split_dicom_float_list(meta.get("pixel_spacing"))
    spacing_y = pixel_spacing[0] if len(pixel_spacing) >= 2 else math.nan
    spacing_x = pixel_spacing[1] if len(pixel_spacing) >= 2 else math.nan
    slice_thickness = parse_float(meta.get("slice_thickness"))
    spacing_between = parse_float(meta.get("spacing_between_slices"))
    pos_summary = summarize_positions(files, meta) if args.compute_slice_spacing else {}
    z_spacing = pos_summary.get("z_spacing_median", "")
    z_for_fov = z_spacing if z_spacing != "" else spacing_between
    if z_for_fov == "" or math.isnan(float(z_for_fov)):
        z_for_fov = slice_thickness

    fov_x = columns * spacing_x if columns and not math.isnan(spacing_x) else ""
    fov_y = rows * spacing_y if rows and not math.isnan(spacing_y) else ""
    try:
        fov_z = (len(files) - 1) * float(z_for_fov) + slice_thickness
    except Exception:
        fov_z = ""

    warnings = []
    if pos_summary.get("z_nonuniform") == 1:
        warnings.append("nonuniform_z_spacing")
    if z_spacing != "" and not math.isnan(slice_thickness) and abs(float(z_spacing) - slice_thickness) > args.spacing_tolerance:
        warnings.append("z_spacing_differs_from_slice_thickness")
    if z_spacing != "" and float(z_spacing) > args.thick_slice_threshold:
        warnings.append("thick_z_spacing")
    if not math.isnan(spacing_x) and not math.isnan(spacing_y) and abs(spacing_x - spacing_y) > args.spacing_tolerance:
        warnings.append("anisotropic_xy_spacing")
    normal = orientation_normal(meta.get("image_orientation_patient", ""))
    if normal is not None and abs(abs(float(normal[2])) - 1.0) > 0.05:
        warnings.append("non_axial_orientation")

    rel_dir = os.path.relpath(directory, root)
    row = {
        "patient_folder": rel_dir.split(os.sep)[0] if rel_dir else "",
        "study_folder": rel_dir.split(os.sep)[1] if len(rel_dir.split(os.sep)) > 1 else "",
        "series_folder": os.path.basename(directory),
        "series_dir": rel_dir,
        "series_id": series_id,
        "n_files": len(files),
        "patient_id": meta.get("patient_id", ""),
        "study_date": meta.get("study_date", ""),
        "study_time": meta.get("study_time", ""),
        "modality": meta.get("modality", ""),
        "body_part_examined": meta.get("body_part_examined", ""),
        "study_description": meta.get("study_description", ""),
        "series_description": meta.get("series_description", ""),
        "manufacturer": meta.get("manufacturer", ""),
        "rows": rows,
        "columns": columns,
        "size_x": columns,
        "size_y": rows,
        "size_z": len(files),
        "pixel_spacing_y": spacing_y if not math.isnan(spacing_y) else "",
        "pixel_spacing_x": spacing_x if not math.isnan(spacing_x) else "",
        "slice_thickness": slice_thickness if not math.isnan(slice_thickness) else "",
        "spacing_between_slices": spacing_between if not math.isnan(spacing_between) else "",
        "fov_x_mm": fov_x,
        "fov_y_mm": fov_y,
        "fov_z_mm": fov_z,
        "image_orientation_patient": meta.get("image_orientation_patient", ""),
        "image_position_first": meta.get("image_position_patient", ""),
        "rescale_intercept": meta.get("rescale_intercept", ""),
        "rescale_slope": meta.get("rescale_slope", ""),
        "convolution_kernel": meta.get("convolution_kernel", ""),
        "kvp": meta.get("kvp", ""),
        "reconstruction_diameter": meta.get("reconstruction_diameter", ""),
        "study_instance_uid": meta.get("study_instance_uid", ""),
        "series_instance_uid": meta.get("series_instance_uid", ""),
        "sop_class_uid": meta.get("sop_class_uid", ""),
        "first_file": os.path.relpath(first_file, root),
        "warnings": ";".join(warnings),
    }
    row.update(pos_summary)
    return row


def find_dicom_directories(root):
    dirs = []
    for directory, _, files in os.walk(root):
        dcm_files = [f for f in files if f.lower().endswith(".dcm")]
        if dcm_files:
            dirs.append(directory)
    return sorted(dirs)


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def aggregate_patient_studies(series_rows):
    groups = defaultdict(list)
    for row in series_rows:
        key = (row.get("patient_id") or row.get("patient_folder"), row.get("study_date") or row.get("study_folder"))
        groups[key].append(row)

    out = []
    for (patient_id, study_date), rows in sorted(groups.items()):
        ct_rows = [r for r in rows if r.get("modality") == "CT"]
        all_rows = rows
        def uniq(key):
            vals = []
            for r in ct_rows:
                v = r.get(key, "")
                if v != "" and v not in vals:
                    vals.append(v)
            return "|".join(str(v) for v in vals)

        out.append(
            {
                "patient_id": patient_id,
                "study_date": study_date,
                "n_image_series": len(all_rows),
                "n_ct_series": len(ct_rows),
                "ct_slice_counts": uniq("n_files"),
                "ct_size_xyz": "|".join(
                    f"{r.get('size_x')}x{r.get('size_y')}x{r.get('size_z')}" for r in ct_rows
                ),
                "ct_spacing_xyz": "|".join(
                    f"{r.get('pixel_spacing_x')},{r.get('pixel_spacing_y')},{r.get('z_spacing_median') or r.get('spacing_between_slices') or r.get('slice_thickness')}"
                    for r in ct_rows
                ),
                "ct_origin_first": "|".join(r.get("image_position_first", "") for r in ct_rows),
                "ct_series_dirs": "|".join(r.get("series_dir", "") for r in ct_rows),
                "grid_mismatch_within_study": int(
                    len(set((r.get("size_x"), r.get("size_y"), r.get("size_z"), r.get("pixel_spacing_x"), r.get("pixel_spacing_y"), r.get("z_spacing_median")) for r in ct_rows)) > 1
                ) if len(ct_rows) > 1 else 0,
                "warnings": ";".join(sorted(set(w for r in ct_rows for w in str(r.get("warnings", "")).split(";") if w))),
            }
        )
    return out


def aggregate_patient_grid(series_rows):
    groups = defaultdict(list)
    for row in series_rows:
        if row.get("modality") != "CT":
            continue
        patient_id = row.get("patient_id") or row.get("patient_folder")
        groups[patient_id].append(row)

    out = []
    for patient_id, rows in sorted(groups.items()):
        grids = set(
            (
                r.get("size_x"),
                r.get("size_y"),
                r.get("size_z"),
                r.get("pixel_spacing_x"),
                r.get("pixel_spacing_y"),
                r.get("z_spacing_median") or r.get("spacing_between_slices") or r.get("slice_thickness"),
            )
            for r in rows
        )
        out.append(
            {
                "patient_id": patient_id,
                "n_ct_studies": len(set(r.get("study_date") for r in rows)),
                "n_ct_series": len(rows),
                "has_multi_timepoint": int(len(set(r.get("study_date") for r in rows)) > 1),
                "has_grid_mismatch_across_time": int(len(grids) > 1),
                "study_dates": "|".join(sorted(set(r.get("study_date", "") for r in rows))),
                "ct_size_xyz": "|".join(
                    f"{r.get('study_date')}:{r.get('size_x')}x{r.get('size_y')}x{r.get('size_z')}" for r in rows
                ),
                "ct_spacing_xyz": "|".join(
                    f"{r.get('study_date')}:{r.get('pixel_spacing_x')},{r.get('pixel_spacing_y')},{r.get('z_spacing_median') or r.get('spacing_between_slices') or r.get('slice_thickness')}"
                    for r in rows
                ),
                "ct_series_dirs": "|".join(r.get("series_dir", "") for r in rows),
            }
        )
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Inspect DICOM image-series geometry and export CSV summaries."
    )
    parser.add_argument("--dcm_root", default="dcm")
    parser.add_argument("--output_dir", default="results/dicom_inspection")
    parser.add_argument("--series_csv", default="")
    parser.add_argument("--non_image_csv", default="")
    parser.add_argument("--study_csv", default="")
    parser.add_argument("--patient_csv", default="")
    parser.add_argument("--compute_slice_spacing", action="store_true", default=True)
    parser.add_argument("--no_compute_slice_spacing", dest="compute_slice_spacing", action="store_false")
    parser.add_argument("--spacing_tolerance", type=float, default=0.05)
    parser.add_argument("--thick_slice_threshold", type=float, default=2.5)
    parser.add_argument("--max_dirs", type=int, default=0)
    args = parser.parse_args()

    root = os.path.abspath(args.dcm_root)
    if not os.path.isdir(root):
        raise FileNotFoundError(root)

    output_dir = args.output_dir
    series_csv = args.series_csv or os.path.join(output_dir, "dicom_image_series_summary.csv")
    non_image_csv = args.non_image_csv or os.path.join(output_dir, "dicom_non_image_or_unreadable_summary.csv")
    study_csv = args.study_csv or os.path.join(output_dir, "dicom_patient_study_summary.csv")
    patient_csv = args.patient_csv or os.path.join(output_dir, "dicom_patient_grid_mismatch_summary.csv")

    directories = find_dicom_directories(root)
    if args.max_dirs and args.max_dirs > 0:
        directories = directories[: args.max_dirs]

    series_rows = []
    non_image_rows = []
    for idx, directory in enumerate(directories, start=1):
        rel_dir = os.path.relpath(directory, root)
        try:
            series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(directory)
        except Exception as exc:
            series_ids = None
            non_image_rows.append(
                {
                    "series_dir": rel_dir,
                    "n_dcm_files": len([f for f in os.listdir(directory) if f.lower().endswith(".dcm")]),
                    "status": "GetGDCMSeriesIDs_failed",
                    "error": str(exc),
                    "suspected_type": "RTSTRUCT" if "RTst" in rel_dir or "RTSTRUCT" in rel_dir.upper() else "",
                }
            )

        if not series_ids:
            if not any(r.get("series_dir") == rel_dir for r in non_image_rows):
                non_image_rows.append(
                    {
                        "series_dir": rel_dir,
                        "n_dcm_files": len([f for f in os.listdir(directory) if f.lower().endswith(".dcm")]),
                        "status": "no_image_series_detected",
                        "error": "",
                        "suspected_type": "RTSTRUCT" if "RTst" in rel_dir or "RTSTRUCT" in rel_dir.upper() else "",
                    }
                )
            continue

        for series_id in series_ids:
            try:
                files = list(sitk.ImageSeriesReader.GetGDCMSeriesFileNames(directory, series_id))
                if not files:
                    raise RuntimeError("series has no files")
                row = series_row(root, directory, series_id, files, args)
                row["scan_index"] = idx
                series_rows.append(row)
            except Exception as exc:
                non_image_rows.append(
                    {
                        "series_dir": rel_dir,
                        "n_dcm_files": len([f for f in os.listdir(directory) if f.lower().endswith(".dcm")]),
                        "status": "series_metadata_failed",
                        "error": str(exc),
                        "suspected_type": "RTSTRUCT" if "RTst" in rel_dir or "RTSTRUCT" in rel_dir.upper() else "",
                    }
                )

    series_fields = [
        "scan_index",
        "patient_folder",
        "study_folder",
        "series_folder",
        "series_dir",
        "patient_id",
        "study_date",
        "study_time",
        "modality",
        "body_part_examined",
        "n_files",
        "size_x",
        "size_y",
        "size_z",
        "pixel_spacing_x",
        "pixel_spacing_y",
        "slice_thickness",
        "spacing_between_slices",
        "z_spacing_median",
        "z_spacing_min",
        "z_spacing_max",
        "z_spacing_std",
        "z_extent_mm",
        "z_nonuniform",
        "fov_x_mm",
        "fov_y_mm",
        "fov_z_mm",
        "image_orientation_patient",
        "image_position_first",
        "slice_position_source",
        "slice_position_count",
        "metadata_read_failures",
        "manufacturer",
        "convolution_kernel",
        "kvp",
        "reconstruction_diameter",
        "rescale_intercept",
        "rescale_slope",
        "series_description",
        "study_description",
        "study_instance_uid",
        "series_instance_uid",
        "sop_class_uid",
        "series_id",
        "first_file",
        "warnings",
    ]
    non_image_fields = ["series_dir", "n_dcm_files", "status", "suspected_type", "error"]
    study_fields = [
        "patient_id",
        "study_date",
        "n_image_series",
        "n_ct_series",
        "ct_slice_counts",
        "ct_size_xyz",
        "ct_spacing_xyz",
        "ct_origin_first",
        "ct_series_dirs",
        "grid_mismatch_within_study",
        "warnings",
    ]
    patient_fields = [
        "patient_id",
        "n_ct_studies",
        "n_ct_series",
        "has_multi_timepoint",
        "has_grid_mismatch_across_time",
        "study_dates",
        "ct_size_xyz",
        "ct_spacing_xyz",
        "ct_series_dirs",
    ]

    write_csv(series_csv, series_rows, series_fields)
    write_csv(non_image_csv, non_image_rows, non_image_fields)
    study_rows = aggregate_patient_studies(series_rows)
    patient_rows = aggregate_patient_grid(series_rows)
    write_csv(study_csv, study_rows, study_fields)
    write_csv(patient_csv, patient_rows, patient_fields)

    print(f"Scanned DICOM directories: {len(directories)}")
    print(f"Image series: {len(series_rows)}")
    print(f"Non-image/unreadable dirs: {len(non_image_rows)}")
    print(f"Saved image series summary: {series_csv}")
    print(f"Saved non-image summary: {non_image_csv}")
    print(f"Saved patient-study summary: {study_csv}")
    print(f"Saved patient grid mismatch summary: {patient_csv}")

    mismatch = [r for r in patient_rows if str(r.get("has_grid_mismatch_across_time")) == "1"]
    if mismatch:
        print(f"Patients with CT grid mismatch across time: {len(mismatch)}")
        for row in mismatch[:20]:
            print(f"  {row['patient_id']}: {row['study_dates']}")


if __name__ == "__main__":
    main()
