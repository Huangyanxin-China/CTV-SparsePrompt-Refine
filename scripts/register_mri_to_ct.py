#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import csv
import os
import re
from collections import defaultdict

import numpy as np
import SimpleITK as sitk


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def patient_id_from_case(case_id):
    m = re.search(r"P\d+", str(case_id))
    return m.group(0) if m else None


def safe_name(text, max_len=120):
    text = re.sub(r"[^A-Za-z0-9_.+-]+", "_", str(text)).strip("_")
    return text[:max_len] if len(text) > max_len else text


def read_tag(reader, key, default=""):
    return reader.GetMetaData(key).strip() if reader.HasMetaDataKey(key) else default


def read_dicom_header(path):
    reader = sitk.ImageFileReader()
    reader.SetFileName(path)
    reader.LoadPrivateTagsOn()
    reader.ReadImageInformation()
    return {
        "modality": read_tag(reader, "0008|0060"),
        "body_part": read_tag(reader, "0018|0015"),
        "series_desc": read_tag(reader, "0008|103e"),
        "protocol": read_tag(reader, "0018|1030"),
        "study_desc": read_tag(reader, "0008|1030"),
        "study_date": read_tag(reader, "0008|0020"),
        "series_number": read_tag(reader, "0020|0011"),
        "image_type": read_tag(reader, "0008|0008"),
        "manufacturer": read_tag(reader, "0008|0070"),
        "model": read_tag(reader, "0008|1090"),
        "rows": read_tag(reader, "0028|0010"),
        "cols": read_tag(reader, "0028|0011"),
        "pixel_spacing": read_tag(reader, "0028|0030"),
        "slice_thickness": read_tag(reader, "0018|0050"),
        "spacing_between_slices": read_tag(reader, "0018|0088"),
        "tr": read_tag(reader, "0018|0080"),
        "te": read_tag(reader, "0018|0081"),
    }


def get_series_files(series_dir):
    ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(series_dir)
    if not ids:
        files = [
            os.path.join(series_dir, f)
            for f in sorted(os.listdir(series_dir))
            if f.lower().endswith(".dcm")
        ]
        return files
    candidates = []
    for sid in ids:
        files = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(series_dir, sid)
        candidates.append((len(files), list(files)))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def read_dicom_series(series_dir):
    files = get_series_files(series_dir)
    if not files:
        raise RuntimeError(f"No DICOM files found in {series_dir}")
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(files)
    reader.MetaDataDictionaryArrayUpdateOn()
    reader.LoadPrivateTagsOn()
    image = reader.Execute()
    if image.GetDimension() != 3:
        raise RuntimeError(f"Expected 3D image, got dimension={image.GetDimension()} from {series_dir}")
    return image, files


def load_ct_rows(csv_path, case_ids=None, patient_ids=None):
    case_filter = set(case_ids or [])
    patient_filter = set(patient_ids or [])
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            case_id = row["case_id"]
            pid = patient_id_from_case(case_id)
            if case_filter and case_id not in case_filter:
                continue
            if patient_filter and pid not in patient_filter:
                continue
            row["patient_id"] = pid
            rows.append(row)
    return rows


def discover_mri_series(
    mri_root,
    patient_ids=None,
    min_files=10,
    include_localizer=False,
    include_reports=False,
):
    patient_filter = set(patient_ids or [])
    rows = []
    for patient in sorted(os.listdir(mri_root)):
        patient_dir = os.path.join(mri_root, patient)
        if not os.path.isdir(patient_dir):
            continue
        if patient_filter and patient not in patient_filter:
            continue
        for dirpath, _, filenames in os.walk(patient_dir):
            dcm_files = [f for f in filenames if f.lower().endswith(".dcm")]
            if not dcm_files:
                continue
            first = os.path.join(dirpath, dcm_files[0])
            try:
                header = read_dicom_header(first)
            except Exception:
                if not include_reports:
                    continue
                header = {"modality": "UNREADABLE", "series_desc": "UNREADABLE", "protocol": ""}
            desc = f"{header.get('series_desc', '')} {header.get('protocol', '')}".lower()
            if header.get("modality") != "MR":
                continue
            if len(dcm_files) < int(min_files):
                continue
            if not include_localizer and ("localizer" in desc or "report" in desc or "phoenix" in desc):
                continue
            row = {
                "patient_id": patient,
                "series_dir": dirpath,
                "num_files": len(dcm_files),
            }
            row.update(header)
            rows.append(row)
    return rows


def keyword_match(series, keywords):
    if not keywords:
        return True
    text = f"{series.get('series_desc', '')} {series.get('protocol', '')} {series.get('image_type', '')}".lower()
    return any(k.lower() in text for k in keywords)


def series_rank(series, prefer_keywords):
    text = f"{series.get('series_desc', '')} {series.get('protocol', '')} {series.get('image_type', '')}".lower()
    rank = 1000
    for i, kw in enumerate(prefer_keywords):
        if kw.lower() in text:
            rank = min(rank, i)
    if "localizer" in text or "resp" in text:
        rank += 100
    return (rank, -int(series.get("num_files", 0)), str(series.get("series_desc", "")))


def write_csv(path, rows, fieldnames):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_for_registration(image, lower=0.5, upper=99.5):
    arr = sitk.GetArrayFromImage(image).astype(np.float32)
    finite = np.isfinite(arr)
    if finite.any():
        lo, hi = np.percentile(arr[finite], [float(lower), float(upper)])
    else:
        lo, hi = 0.0, 1.0
    if hi <= lo:
        hi = lo + 1.0
    arr = np.clip(arr, lo, hi)
    arr = (arr - lo) / (hi - lo)
    out = sitk.GetImageFromArray(arr.astype(np.float32))
    out.CopyInformation(image)
    return out


def make_initial_transform(fixed, moving, transform_type="rigid"):
    if transform_type == "affine":
        base = sitk.AffineTransform(3)
    else:
        base = sitk.Euler3DTransform()
    return sitk.CenteredTransformInitializer(
        fixed,
        moving,
        base,
        sitk.CenteredTransformInitializerFilter.GEOMETRY,
    )


def register_mri_to_ct(
    fixed_ct,
    moving_mri,
    transform_type="rigid",
    sampling_percentage=0.02,
    iterations=200,
):
    fixed = normalize_for_registration(sitk.Cast(fixed_ct, sitk.sitkFloat32))
    moving = normalize_for_registration(sitk.Cast(moving_mri, sitk.sitkFloat32))
    initial = make_initial_transform(fixed, moving, transform_type=transform_type)

    registration = sitk.ImageRegistrationMethod()
    registration.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
    registration.SetMetricSamplingStrategy(registration.RANDOM)
    registration.SetMetricSamplingPercentage(float(sampling_percentage), seed=42)
    registration.SetInterpolator(sitk.sitkLinear)
    registration.SetOptimizerAsRegularStepGradientDescent(
        learningRate=2.0,
        minStep=1e-4,
        numberOfIterations=int(iterations),
        gradientMagnitudeTolerance=1e-8,
    )
    registration.SetOptimizerScalesFromPhysicalShift()
    registration.SetShrinkFactorsPerLevel([4, 2, 1])
    registration.SetSmoothingSigmasPerLevel([2, 1, 0])
    registration.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    registration.SetInitialTransform(initial, inPlace=False)
    final_transform = registration.Execute(fixed, moving)
    return final_transform, registration.GetMetricValue(), registration.GetOptimizerStopConditionDescription()


def resample_to_fixed(moving, fixed, transform, default_value=0.0):
    return sitk.Resample(
        moving,
        fixed,
        transform,
        sitk.sitkLinear,
        float(default_value),
        moving.GetPixelID(),
    )


def image_summary(image):
    return {
        "size": "x".join(map(str, image.GetSize())),
        "spacing": "x".join(f"{v:.4g}" for v in image.GetSpacing()),
        "origin": "x".join(f"{v:.4g}" for v in image.GetOrigin()),
    }


def main():
    parser = argparse.ArgumentParser(description="Register patient MRI DICOM series to CT ROI images.")
    parser.add_argument("--mri_root", default="/share3/home/huangyanxin/20260422")
    parser.add_argument("--ct_csv", default="data/roi_1mm/roi_1mm.csv")
    parser.add_argument("--output_dir", default="data/mri_ct_registration")
    parser.add_argument("--case_id", action="append", default=None, help="CT case_id to process. Can be repeated.")
    parser.add_argument("--patient_id", action="append", default=None, help="Patient id. Can be repeated.")
    parser.add_argument("--series_keyword", action="append", default=None, help="Keep MR series containing this keyword. Can be repeated.")
    parser.add_argument(
        "--prefer_keywords",
        default="t2,t1_vibe_fs,t1_vibe_dixon,adc,tracew,diff",
        help="Comma-separated priority list used when max_series_per_case is set.",
    )
    parser.add_argument("--max_series_per_case", type=int, default=1)
    parser.add_argument("--min_files", type=int, default=10)
    parser.add_argument("--list_only", action="store_true")
    parser.add_argument("--include_localizer", action="store_true")
    parser.add_argument("--include_reports", action="store_true")
    parser.add_argument("--transform", choices=["rigid", "affine"], default="rigid")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--sampling_percentage", type=float, default=0.02)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    ct_rows = load_ct_rows(args.ct_csv, case_ids=args.case_id, patient_ids=args.patient_id)
    if not ct_rows:
        raise RuntimeError("No CT rows matched the requested case_id/patient_id.")
    patient_ids = sorted({r["patient_id"] for r in ct_rows if r.get("patient_id")})

    series_rows = discover_mri_series(
        args.mri_root,
        patient_ids=patient_ids,
        min_files=args.min_files,
        include_localizer=args.include_localizer,
        include_reports=args.include_reports,
    )
    keywords = args.series_keyword or []
    if keywords:
        series_rows = [s for s in series_rows if keyword_match(s, keywords)]

    prefer = [v for v in str(args.prefer_keywords).split(",") if v]
    series_by_patient = defaultdict(list)
    for s in series_rows:
        series_by_patient[s["patient_id"]].append(s)
    for pid in series_by_patient:
        series_by_patient[pid].sort(key=lambda s: series_rank(s, prefer))

    index_rows = []
    for s in series_rows:
        index_rows.append(
            {
                "patient_id": s["patient_id"],
                "num_files": s["num_files"],
                "modality": s.get("modality", ""),
                "body_part": s.get("body_part", ""),
                "study_date": s.get("study_date", ""),
                "series_number": s.get("series_number", ""),
                "series_desc": s.get("series_desc", ""),
                "protocol": s.get("protocol", ""),
                "image_type": s.get("image_type", ""),
                "series_dir": s["series_dir"],
            }
        )
    index_path = os.path.join(args.output_dir, "mri_series_index.csv")
    write_csv(
        index_path,
        index_rows,
        [
            "patient_id",
            "num_files",
            "modality",
            "body_part",
            "study_date",
            "series_number",
            "series_desc",
            "protocol",
            "image_type",
            "series_dir",
        ],
    )
    print(f"Saved MRI series index: {index_path}")

    if args.list_only:
        for pid in patient_ids:
            print(f"\n{pid}: {len(series_by_patient.get(pid, []))} MR series")
            for s in series_by_patient.get(pid, [])[: max(int(args.max_series_per_case), 20)]:
                print(f"  files={s['num_files']:3d} date={s.get('study_date','')} desc={s.get('series_desc','')} dir={s['series_dir']}")
        return

    result_rows = []
    for ct_row in ct_rows:
        case_id = ct_row["case_id"]
        pid = ct_row["patient_id"]
        fixed_path = ct_row["roi_1mm_image_path"]
        patient_series = series_by_patient.get(pid, [])
        if not patient_series:
            print(f"Skipping {case_id}: no MR series found for {pid}.")
            continue
        if int(args.max_series_per_case) > 0:
            patient_series = patient_series[: int(args.max_series_per_case)]

        fixed = sitk.ReadImage(fixed_path)
        for i, series in enumerate(patient_series, 1):
            desc = safe_name(series.get("series_desc") or series.get("protocol") or f"series{i}")
            out_root = os.path.join(args.output_dir, case_id, f"{i:02d}_{desc}")
            ensure_dir(out_root)
            registered_path = os.path.join(out_root, "mr_registered_to_ct.nii.gz")
            transform_path = os.path.join(out_root, "mr_to_ct.tfm")
            original_path = os.path.join(out_root, "mr_original.nii.gz")
            if os.path.exists(registered_path) and not args.overwrite:
                print(f"Skip existing: {registered_path}")
                continue

            print(f"Registering {pid} {case_id}: {series.get('series_desc','')} -> CT ROI")
            try:
                moving, files = read_dicom_series(series["series_dir"])
                sitk.WriteImage(moving, original_path)
                transform, metric, stop = register_mri_to_ct(
                    fixed,
                    moving,
                    transform_type=args.transform,
                    sampling_percentage=args.sampling_percentage,
                    iterations=args.iterations,
                )
                registered = resample_to_fixed(moving, fixed, transform, default_value=0.0)
                sitk.WriteImage(registered, registered_path)
                sitk.WriteTransform(transform, transform_path)
                status = "ok"
                error = ""
            except Exception as e:
                status = "failed"
                metric = ""
                stop = ""
                error = repr(e)
                print(f"FAILED {case_id} {series.get('series_desc','')}: {error}")

            fixed_sum = image_summary(fixed)
            moving_sum = image_summary(moving) if status == "ok" else {"size": "", "spacing": "", "origin": ""}
            result_rows.append(
                {
                    "case_id": case_id,
                    "patient_id": pid,
                    "ct_path": fixed_path,
                    "series_desc": series.get("series_desc", ""),
                    "protocol": series.get("protocol", ""),
                    "study_date": series.get("study_date", ""),
                    "series_dir": series["series_dir"],
                    "status": status,
                    "metric": metric,
                    "stop_condition": stop,
                    "registered_mri_path": registered_path if status == "ok" else "",
                    "original_mri_path": original_path if status == "ok" else "",
                    "transform_path": transform_path if status == "ok" else "",
                    "ct_size": fixed_sum["size"],
                    "ct_spacing": fixed_sum["spacing"],
                    "mr_size": moving_sum["size"],
                    "mr_spacing": moving_sum["spacing"],
                    "error": error,
                }
            )

    summary_path = os.path.join(args.output_dir, "registration_summary.csv")
    write_csv(
        summary_path,
        result_rows,
        [
            "case_id",
            "patient_id",
            "ct_path",
            "series_desc",
            "protocol",
            "study_date",
            "series_dir",
            "status",
            "metric",
            "stop_condition",
            "registered_mri_path",
            "original_mri_path",
            "transform_path",
            "ct_size",
            "ct_spacing",
            "mr_size",
            "mr_spacing",
            "error",
        ],
    )
    print(f"Saved registration summary: {summary_path}")


if __name__ == "__main__":
    main()
