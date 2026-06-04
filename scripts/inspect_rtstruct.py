#!/usr/bin/env python
import argparse
import csv
import json
import math
import os
from collections import Counter, defaultdict

import numpy as np
import pydicom


RTSTRUCT_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.481.3"


def clean(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return math.nan


def safe_int(value):
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return 0


def relpath(path, root):
    return os.path.relpath(path, root)


def iter_dicom_files(root):
    for directory, _, files in os.walk(root):
        for name in sorted(files):
            if name.lower().endswith(".dcm"):
                yield os.path.join(directory, name)


def ds_get(ds, name, default=""):
    return clean(getattr(ds, name, default))


def is_rtstruct(ds, path=""):
    modality = clean(getattr(ds, "Modality", ""))
    sop_class = clean(getattr(ds, "SOPClassUID", ""))
    return modality == "RTSTRUCT" or sop_class == RTSTRUCT_SOP_CLASS_UID or "RTst" in path


def parse_contour_data(contour):
    data = getattr(contour, "ContourData", None)
    if data is None:
        return np.empty((0, 3), dtype=np.float64)
    values = np.asarray([safe_float(v) for v in data], dtype=np.float64)
    if values.size < 3:
        return np.empty((0, 3), dtype=np.float64)
    usable = (values.size // 3) * 3
    return values[:usable].reshape(-1, 3)


def bbox_from_points(points):
    if points.size == 0:
        return {
            "x_min": "",
            "x_max": "",
            "y_min": "",
            "y_max": "",
            "z_min": "",
            "z_max": "",
        }
    return {
        "x_min": float(np.min(points[:, 0])),
        "x_max": float(np.max(points[:, 0])),
        "y_min": float(np.min(points[:, 1])),
        "y_max": float(np.max(points[:, 1])),
        "z_min": float(np.min(points[:, 2])),
        "z_max": float(np.max(points[:, 2])),
    }


def get_referenced_sop_uids(contour):
    out = []
    for item in getattr(contour, "ContourImageSequence", []) or []:
        uid = clean(getattr(item, "ReferencedSOPInstanceUID", ""))
        if uid:
            out.append(uid)
    return out


def build_image_sop_index(root):
    sop_index = {}
    series_index = defaultdict(lambda: {"n_slices": 0, "series_dir": "", "patient_id": "", "study_date": ""})
    unreadable = []
    for path in iter_dicom_files(root):
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=True, specific_tags=[
                "SOPClassUID",
                "SOPInstanceUID",
                "Modality",
                "PatientID",
                "StudyDate",
                "SeriesInstanceUID",
                "StudyInstanceUID",
                "ImagePositionPatient",
                "InstanceNumber",
            ])
        except Exception as exc:
            unreadable.append({"path": relpath(path, root), "error": str(exc)})
            continue
        if is_rtstruct(ds, path):
            continue
        sop_uid = clean(getattr(ds, "SOPInstanceUID", ""))
        series_uid = clean(getattr(ds, "SeriesInstanceUID", ""))
        if not sop_uid or not series_uid:
            continue
        series_dir = relpath(os.path.dirname(path), root)
        ipp = getattr(ds, "ImagePositionPatient", None)
        z = ""
        if ipp is not None and len(ipp) >= 3:
            z = safe_float(ipp[2])
        item = {
            "sop_instance_uid": sop_uid,
            "series_instance_uid": series_uid,
            "study_instance_uid": clean(getattr(ds, "StudyInstanceUID", "")),
            "patient_id": clean(getattr(ds, "PatientID", "")),
            "study_date": clean(getattr(ds, "StudyDate", "")),
            "modality": clean(getattr(ds, "Modality", "")),
            "instance_number": clean(getattr(ds, "InstanceNumber", "")),
            "image_position_z": z,
            "series_dir": series_dir,
            "file_path": relpath(path, root),
        }
        sop_index[sop_uid] = item
        s = series_index[series_uid]
        s["n_slices"] += 1
        s["series_dir"] = series_dir
        s["patient_id"] = item["patient_id"]
        s["study_date"] = item["study_date"]
        s["study_instance_uid"] = item["study_instance_uid"]
    return sop_index, dict(series_index), unreadable


def load_series_index_from_csv(path):
    if not path or not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            uid = clean(row.get("series_instance_uid", ""))
            if not uid:
                continue
            out[uid] = {
                "n_slices": safe_int(row.get("n_files", 0)),
                "series_dir": clean(row.get("series_dir", "")),
                "patient_id": clean(row.get("patient_id", "")),
                "study_date": clean(row.get("study_date", "")),
                "study_instance_uid": clean(row.get("study_instance_uid", "")),
            }
    return out


def find_rtstruct_files(root, case_ids=None, hint="RTst"):
    case_set = set(case_ids or [])
    candidates = []
    for path in iter_dicom_files(root):
        rel = relpath(path, root)
        if hint and hint not in rel and "RTSTRUCT" not in rel.upper():
            continue
        candidates.append(path)

    # If the directory naming convention does not expose RTSTRUCT, fall back to
    # scanning all DICOM files. The local dataset uses RTst directories, so this
    # path is normally not used.
    if not candidates:
        candidates = list(iter_dicom_files(root))

    out = []
    read_errors = []
    for path in candidates:
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=True, specific_tags=[
                "SOPClassUID",
                "Modality",
                "PatientID",
                "StudyDate",
            ])
        except Exception as exc:
            read_errors.append({"path": relpath(path, root), "error": str(exc)})
            continue
        if not is_rtstruct(ds, path):
            continue
        patient_id = clean(getattr(ds, "PatientID", ""))
        if case_set and patient_id not in case_set:
            continue
        out.append(path)
    return sorted(out), read_errors


def roi_name_target_flag(name):
    upper = str(name).upper()
    keywords = ("GTV", "CTV", "PTV", "ITV", "TARGET", "TUMOR", "TUMOUR")
    return int(any(k in upper for k in keywords))


def map_roi_definitions(ds):
    roi_defs = {}
    for roi in getattr(ds, "StructureSetROISequence", []) or []:
        number = safe_int(getattr(roi, "ROINumber", 0))
        roi_defs[number] = {
            "roi_number": number,
            "roi_name": clean(getattr(roi, "ROIName", "")),
            "roi_generation_algorithm": clean(getattr(roi, "ROIGenerationAlgorithm", "")),
            "referenced_frame_of_reference_uid": clean(getattr(roi, "ReferencedFrameOfReferenceUID", "")),
            "roi_description": clean(getattr(roi, "ROIDescription", "")),
        }
    return roi_defs


def map_roi_observations(ds):
    out = {}
    for obs in getattr(ds, "RTROIObservationsSequence", []) or []:
        number = safe_int(getattr(obs, "ReferencedROINumber", 0))
        out[number] = {
            "observation_number": clean(getattr(obs, "ObservationNumber", "")),
            "observation_label": clean(getattr(obs, "ROIObservationLabel", "")),
            "interpreted_type": clean(getattr(obs, "RTROIInterpretedType", "")),
            "interpreter": clean(getattr(obs, "ROIInterpreter", "")),
        }
    return out


def referenced_series_from_rtstruct(ds):
    rows = []
    for frame in getattr(ds, "ReferencedFrameOfReferenceSequence", []) or []:
        frame_uid = clean(getattr(frame, "FrameOfReferenceUID", ""))
        for study in getattr(frame, "RTReferencedStudySequence", []) or []:
            ref_study_uid = clean(getattr(study, "ReferencedSOPInstanceUID", ""))
            for series in getattr(study, "RTReferencedSeriesSequence", []) or []:
                series_uid = clean(getattr(series, "SeriesInstanceUID", ""))
                contour_images = getattr(series, "ContourImageSequence", []) or []
                rows.append(
                    {
                        "frame_of_reference_uid": frame_uid,
                        "referenced_study_sop_uid": ref_study_uid,
                        "referenced_series_uid": series_uid,
                        "n_referenced_images": len(contour_images),
                        "referenced_sop_uids": "|".join(
                            clean(getattr(img, "ReferencedSOPInstanceUID", "")) for img in contour_images
                        ),
                    }
                )
    return rows


def inspect_rtstruct_file(path, root, sop_index, series_index, save_points=False):
    ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
    rel = relpath(path, root)
    rt_dir = relpath(os.path.dirname(path), root)
    roi_defs = map_roi_definitions(ds)
    observations = map_roi_observations(ds)
    ref_series_rows = referenced_series_from_rtstruct(ds)

    contour_by_roi = {}
    for roi_contour in getattr(ds, "ROIContourSequence", []) or []:
        roi_number = safe_int(getattr(roi_contour, "ReferencedROINumber", 0))
        contour_by_roi[roi_number] = roi_contour

    file_row = {
        "rtstruct_file": rel,
        "rtstruct_dir": rt_dir,
        "patient_id": ds_get(ds, "PatientID"),
        "patient_name": ds_get(ds, "PatientName"),
        "study_date": ds_get(ds, "StudyDate"),
        "study_time": ds_get(ds, "StudyTime"),
        "modality": ds_get(ds, "Modality"),
        "structure_set_label": ds_get(ds, "StructureSetLabel"),
        "structure_set_name": ds_get(ds, "StructureSetName"),
        "structure_set_date": ds_get(ds, "StructureSetDate"),
        "structure_set_time": ds_get(ds, "StructureSetTime"),
        "study_instance_uid": ds_get(ds, "StudyInstanceUID"),
        "series_instance_uid": ds_get(ds, "SeriesInstanceUID"),
        "frame_of_reference_uid": ds_get(ds, "FrameOfReferenceUID"),
        "sop_instance_uid": ds_get(ds, "SOPInstanceUID"),
        "sop_class_uid": ds_get(ds, "SOPClassUID"),
        "n_rois": len(roi_defs),
        "n_roi_contours": len(contour_by_roi),
        "roi_names": "|".join(v["roi_name"] for _, v in sorted(roi_defs.items())),
        "target_like_roi_names": "|".join(
            v["roi_name"] for _, v in sorted(roi_defs.items()) if roi_name_target_flag(v["roi_name"])
        ),
        "referenced_series_uids": "|".join(sorted({r["referenced_series_uid"] for r in ref_series_rows if r["referenced_series_uid"]})),
        "referenced_series_dirs": "|".join(
            sorted(
                {
                    series_index.get(r["referenced_series_uid"], {}).get("series_dir", "")
                    for r in ref_series_rows
                    if r["referenced_series_uid"] and series_index.get(r["referenced_series_uid"], {}).get("series_dir", "")
                }
            )
        ),
    }

    roi_rows = []
    contour_rows = []
    point_rows = []
    for roi_number, roi_def in sorted(roi_defs.items()):
        roi_contour = contour_by_roi.get(roi_number)
        observation = observations.get(roi_number, {})
        color = ""
        contours = []
        if roi_contour is not None:
            color = "\\".join(str(v) for v in getattr(roi_contour, "ROIDisplayColor", []) or [])
            contours = list(getattr(roi_contour, "ContourSequence", []) or [])

        all_points = []
        contour_types = Counter()
        referenced_sops = []
        referenced_series = []
        referenced_dirs = []
        missing_refs = 0
        z_values = []
        for contour_idx, contour in enumerate(contours):
            points = parse_contour_data(contour)
            if points.size:
                all_points.append(points)
                z_values.extend(points[:, 2].tolist())
            contour_type = clean(getattr(contour, "ContourGeometricType", ""))
            if contour_type:
                contour_types[contour_type] += 1
            refs = get_referenced_sop_uids(contour)
            referenced_sops.extend(refs)
            mapped_series = []
            mapped_dirs = []
            for sop_uid in refs:
                item = sop_index.get(sop_uid)
                if item is None:
                    missing_refs += 1
                    continue
                mapped_series.append(item["series_instance_uid"])
                mapped_dirs.append(item["series_dir"])
            referenced_series.extend(mapped_series)
            referenced_dirs.extend(mapped_dirs)

            bbox = bbox_from_points(points)
            contour_row = {
                "rtstruct_file": rel,
                "patient_id": file_row["patient_id"],
                "study_date": file_row["study_date"],
                "roi_number": roi_number,
                "roi_name": roi_def["roi_name"],
                "contour_index": contour_idx,
                "contour_geometric_type": contour_type,
                "n_points": int(points.shape[0]),
                "referenced_sop_uids": "|".join(refs),
                "mapped_series_uids": "|".join(sorted(set(mapped_series))),
                "mapped_series_dirs": "|".join(sorted(set(mapped_dirs))),
            }
            contour_row.update(bbox)
            contour_rows.append(contour_row)

            if save_points and points.size:
                for point_idx, point in enumerate(points):
                    point_rows.append(
                        {
                            "rtstruct_file": rel,
                            "patient_id": file_row["patient_id"],
                            "study_date": file_row["study_date"],
                            "roi_number": roi_number,
                            "roi_name": roi_def["roi_name"],
                            "contour_index": contour_idx,
                            "point_index": point_idx,
                            "x": float(point[0]),
                            "y": float(point[1]),
                            "z": float(point[2]),
                            "referenced_sop_uids": "|".join(refs),
                        }
                    )

        if all_points:
            merged = np.concatenate(all_points, axis=0)
            bbox = bbox_from_points(merged)
        else:
            bbox = bbox_from_points(np.empty((0, 3), dtype=np.float64))
        unique_z = sorted({round(float(z), 3) for z in z_values})
        roi_rows.append(
            {
                "rtstruct_file": rel,
                "rtstruct_dir": rt_dir,
                "patient_id": file_row["patient_id"],
                "study_date": file_row["study_date"],
                "roi_number": roi_number,
                "roi_name": roi_def["roi_name"],
                "target_like": roi_name_target_flag(roi_def["roi_name"]),
                "roi_generation_algorithm": roi_def.get("roi_generation_algorithm", ""),
                "roi_description": roi_def.get("roi_description", ""),
                "referenced_frame_of_reference_uid": roi_def.get("referenced_frame_of_reference_uid", ""),
                "observation_label": observation.get("observation_label", ""),
                "interpreted_type": observation.get("interpreted_type", ""),
                "interpreter": observation.get("interpreter", ""),
                "display_color": color,
                "n_contours": len(contours),
                "n_points_total": int(sum(parse_contour_data(c).shape[0] for c in contours)),
                "n_unique_z": len(unique_z),
                "z_values": "|".join(str(v) for v in unique_z),
                "contour_types": "|".join(f"{k}:{v}" for k, v in sorted(contour_types.items())),
                "n_referenced_sop_uids": len(set(referenced_sops)),
                "missing_referenced_sop_count": missing_refs,
                "referenced_series_uids": "|".join(sorted(set(referenced_series))),
                "referenced_series_dirs": "|".join(sorted(set(referenced_dirs))),
                **bbox,
            }
        )

    ref_rows = []
    for row in ref_series_rows:
        series_uid = row["referenced_series_uid"]
        s = series_index.get(series_uid, {})
        ref_rows.append(
            {
                "rtstruct_file": rel,
                "patient_id": file_row["patient_id"],
                "study_date": file_row["study_date"],
                "referenced_series_uid": series_uid,
                "matched_series_dir": s.get("series_dir", ""),
                "matched_patient_id": s.get("patient_id", ""),
                "matched_study_date": s.get("study_date", ""),
                "matched_n_slices": s.get("n_slices", ""),
                "frame_of_reference_uid": row["frame_of_reference_uid"],
                "n_referenced_images": row["n_referenced_images"],
            }
        )

    return file_row, roi_rows, contour_rows, ref_rows, point_rows


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Inspect RTSTRUCT DICOM files and contour geometry.")
    parser.add_argument("--dcm_root", default="dcm")
    parser.add_argument("--output_dir", default="results/dicom_inspection")
    parser.add_argument(
        "--series_summary_csv",
        default="results/dicom_inspection/dicom_image_series_summary.csv",
        help="Optional CT series summary used to match RTSTRUCT referenced series without re-scanning every slice.",
    )
    parser.add_argument(
        "--build_sop_index",
        action="store_true",
        help="Slow but detailed: build ReferencedSOPInstanceUID -> CT slice mapping for each contour.",
    )
    parser.add_argument("--rtstruct_hint", default="RTst")
    parser.add_argument("--case_id", action="append", default=None, help="Filter by PatientID.")
    parser.add_argument("--save_contour_points", action="store_true")
    parser.add_argument("--max_files", type=int, default=0)
    args = parser.parse_args()

    root = os.path.abspath(args.dcm_root)
    if not os.path.isdir(root):
        raise FileNotFoundError(root)

    series_index = load_series_index_from_csv(args.series_summary_csv)
    sop_index = {}
    unreadable = []
    if args.build_sop_index:
        sop_index, sop_series_index, unreadable = build_image_sop_index(root)
        series_index.update(sop_series_index)

    rt_files, read_errors = find_rtstruct_files(root, case_ids=args.case_id, hint=args.rtstruct_hint)
    if args.max_files and args.max_files > 0:
        rt_files = rt_files[: args.max_files]

    file_rows = []
    roi_rows = []
    contour_rows = []
    ref_rows = []
    point_rows = []
    rt_errors = []
    for path in rt_files:
        try:
            frow, rrows, crows, refs, prows = inspect_rtstruct_file(
                path, root, sop_index, series_index, save_points=args.save_contour_points
            )
            file_rows.append(frow)
            roi_rows.extend(rrows)
            contour_rows.extend(crows)
            ref_rows.extend(refs)
            point_rows.extend(prows)
        except Exception as exc:
            rt_errors.append({"rtstruct_file": relpath(path, root), "error": str(exc)})

    file_fields = [
        "rtstruct_file",
        "rtstruct_dir",
        "patient_id",
        "patient_name",
        "study_date",
        "study_time",
        "modality",
        "structure_set_label",
        "structure_set_name",
        "structure_set_date",
        "structure_set_time",
        "n_rois",
        "n_roi_contours",
        "roi_names",
        "target_like_roi_names",
        "referenced_series_uids",
        "referenced_series_dirs",
        "study_instance_uid",
        "series_instance_uid",
        "frame_of_reference_uid",
        "sop_instance_uid",
        "sop_class_uid",
    ]
    roi_fields = [
        "rtstruct_file",
        "rtstruct_dir",
        "patient_id",
        "study_date",
        "roi_number",
        "roi_name",
        "target_like",
        "roi_generation_algorithm",
        "roi_description",
        "referenced_frame_of_reference_uid",
        "observation_label",
        "interpreted_type",
        "interpreter",
        "display_color",
        "n_contours",
        "n_points_total",
        "n_unique_z",
        "z_values",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "z_min",
        "z_max",
        "contour_types",
        "n_referenced_sop_uids",
        "missing_referenced_sop_count",
        "referenced_series_uids",
        "referenced_series_dirs",
    ]
    contour_fields = [
        "rtstruct_file",
        "patient_id",
        "study_date",
        "roi_number",
        "roi_name",
        "contour_index",
        "contour_geometric_type",
        "n_points",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "z_min",
        "z_max",
        "referenced_sop_uids",
        "mapped_series_uids",
        "mapped_series_dirs",
    ]
    ref_fields = [
        "rtstruct_file",
        "patient_id",
        "study_date",
        "referenced_series_uid",
        "matched_series_dir",
        "matched_patient_id",
        "matched_study_date",
        "matched_n_slices",
        "frame_of_reference_uid",
        "n_referenced_images",
    ]
    point_fields = [
        "rtstruct_file",
        "patient_id",
        "study_date",
        "roi_number",
        "roi_name",
        "contour_index",
        "point_index",
        "x",
        "y",
        "z",
        "referenced_sop_uids",
    ]

    out = args.output_dir
    write_csv(os.path.join(out, "rtstruct_file_summary.csv"), file_rows, file_fields)
    write_csv(os.path.join(out, "rtstruct_roi_summary.csv"), roi_rows, roi_fields)
    write_csv(os.path.join(out, "rtstruct_contour_summary.csv"), contour_rows, contour_fields)
    write_csv(os.path.join(out, "rtstruct_referenced_series_summary.csv"), ref_rows, ref_fields)
    if args.save_contour_points:
        write_csv(os.path.join(out, "rtstruct_contour_points.csv"), point_rows, point_fields)
    write_json(
        os.path.join(out, "rtstruct_parse_errors.json"),
        {
            "image_index_unreadable": unreadable,
            "rtstruct_read_errors": read_errors,
            "rtstruct_parse_errors": rt_errors,
        },
    )

    print(f"Indexed image SOPs: {len(sop_index)}")
    print(f"Indexed image series: {len(series_index)}")
    print(f"RTSTRUCT files: {len(rt_files)}")
    print(f"Parsed RTSTRUCT files: {len(file_rows)}")
    print(f"ROI rows: {len(roi_rows)}")
    print(f"Contour rows: {len(contour_rows)}")
    print(f"Saved: {os.path.join(out, 'rtstruct_file_summary.csv')}")
    print(f"Saved: {os.path.join(out, 'rtstruct_roi_summary.csv')}")
    print(f"Saved: {os.path.join(out, 'rtstruct_contour_summary.csv')}")
    print(f"Saved: {os.path.join(out, 'rtstruct_referenced_series_summary.csv')}")
    if args.save_contour_points:
        print(f"Saved: {os.path.join(out, 'rtstruct_contour_points.csv')}")
    if rt_errors:
        print(f"RTSTRUCT parse errors: {len(rt_errors)}")


if __name__ == "__main__":
    main()
