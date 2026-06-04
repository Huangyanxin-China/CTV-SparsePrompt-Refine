from __future__ import annotations

import csv
import os
from pathlib import Path

import pydicom


ROOT = Path(__file__).resolve().parent
OUT_CSV = ROOT / "gtv_cases.csv"
KEYWORD = "GTV"


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def collect_names(ds) -> list[str]:
    names: list[str] = []

    for item in getattr(ds, "StructureSetROISequence", []) or []:
        name = as_text(getattr(item, "ROIName", "")).strip()
        if name:
            names.append(name)

    for item in getattr(ds, "SegmentSequence", []) or []:
        for attr in ("SegmentLabel", "SegmentDescription"):
            name = as_text(getattr(item, attr, "")).strip()
            if name:
                names.append(name)

    for item in getattr(ds, "RTROIObservationsSequence", []) or []:
        for attr in ("ROIObservationLabel", "RTROIInterpretedType"):
            name = as_text(getattr(item, attr, "")).strip()
            if name:
                names.append(name)

    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        key = name.casefold()
        if key not in seen:
            unique.append(name)
            seen.add(key)
    return unique


def patient_from_path(path: Path) -> tuple[str, str]:
    parts = path.relative_to(ROOT).parts
    batch = parts[0] if len(parts) > 0 else ""
    patient = ""
    for part in parts:
        if part.startswith("patient_"):
            patient = part
            break
    return batch, patient


def find_uid_file(ct_dir: Path, uid: str) -> Path | None:
    exact_names = [f"{uid}.DCM", f"{uid}.dcm", uid]
    for name in exact_names:
        path = ct_dir / name
        if path.is_file():
            return path

    for path in ct_dir.rglob("*"):
        if path.is_file() and uid in path.name:
            return path
    return None


def referenced_structure_uids(plan_ds) -> list[str]:
    uids: list[str] = []
    for item in getattr(plan_ds, "ReferencedStructureSetSequence", []) or []:
        uid = as_text(getattr(item, "ReferencedSOPInstanceUID", "")).strip()
        if uid:
            uids.append(uid)
    return uids


def main() -> None:
    plan_files = []
    for batch in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        for patient in sorted(p for p in batch.iterdir() if p.is_dir()):
            plan_dir = patient / "DICOM_PLAN"
            if plan_dir.is_dir():
                plan_files.extend(p for p in plan_dir.rglob("*") if p.is_file())

    rows = []
    unreadable = 0
    referenced_structures = 0
    found_structures = 0
    missing_structures = []

    for idx, plan_path in enumerate(plan_files, 1):
        try:
            plan_ds = pydicom.dcmread(str(plan_path), force=True, stop_before_pixels=True)
        except Exception:
            unreadable += 1
            continue

        modality = as_text(getattr(plan_ds, "Modality", "")).strip()
        if modality != "RTPLAN":
            continue

        batch, patient = patient_from_path(plan_path)
        patient_dir = plan_path.parent.parent
        ct_dir = patient_dir / "CT_SET"
        for struct_uid in referenced_structure_uids(plan_ds):
            referenced_structures += 1
            struct_path = find_uid_file(ct_dir, struct_uid) if ct_dir.is_dir() else None
            if struct_path is None:
                missing_structures.append((batch, patient, struct_uid))
                continue

            found_structures += 1
            try:
                ds = pydicom.dcmread(str(struct_path), force=True, stop_before_pixels=True)
            except Exception:
                unreadable += 1
                continue

            names = collect_names(ds)

            matched = [name for name in names if KEYWORD.casefold() in name.casefold()]
            if matched:
                rows.append(
                    {
                        "batch": batch,
                        "patient": patient,
                        "matched_names": "; ".join(matched),
                        "structure_file": str(struct_path),
                        "plan_file": str(plan_path),
                        "structure_uid": struct_uid,
                        "all_roi_or_segment_names": "; ".join(names),
                    }
                )

        if idx % 50 == 0:
            print(f"scanned {idx}/{len(plan_files)} RT plan files...", flush=True)

    rows.sort(key=lambda r: (r["batch"], r["patient"], r["structure_file"]))
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "batch",
                "patient",
                "matched_names",
                "structure_file",
                "plan_file",
                "structure_uid",
                "all_roi_or_segment_names",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    unique_patients = sorted({(r["batch"], r["patient"]) for r in rows})
    print(f"RT plan files scanned: {len(plan_files)}")
    print(f"Referenced structure sets: {referenced_structures}")
    print(f"Structure files found: {found_structures}")
    print(f"Structure files missing: {len(missing_structures)}")
    print(f"Unreadable files: {unreadable}")
    print(f"Files with {KEYWORD}: {len(rows)}")
    print(f"Patients with {KEYWORD}: {len(unique_patients)}")
    print(f"CSV: {OUT_CSV}")
    for batch, patient in unique_patients:
        patient_rows = [r for r in rows if r["batch"] == batch and r["patient"] == patient]
        names = sorted({name for r in patient_rows for name in r["matched_names"].split("; ") if name})
        print(f"{batch}\\{patient}: {', '.join(names)}")


if __name__ == "__main__":
    main()
