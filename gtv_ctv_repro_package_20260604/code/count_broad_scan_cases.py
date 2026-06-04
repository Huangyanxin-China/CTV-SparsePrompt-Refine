from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pydicom

from export_gtv_rtstruct_masks import (
    choose_ct_series,
    read_ct_headers,
    referenced_image_uids,
    roi_number_to_name,
    structure_frame_uid,
)
from inventory_rtstruct_rois import all_referenced_structures, unique_gtv_structures
from prepare_nnunet_datasets import clean_patient_id, dicom_date_time
from rescreen_broad_labels import broad_categories


def roi_numbers_with_contours(rtstruct) -> set[int]:
    nums: set[int] = set()
    for item in getattr(rtstruct, "ROIContourSequence", []) or []:
        contours = getattr(item, "ContourSequence", []) or []
        has_data = any(len(getattr(c, "ContourData", []) or []) >= 9 for c in contours)
        if not has_data:
            continue
        try:
            nums.add(int(getattr(item, "ReferencedROINumber")))
        except Exception:
            continue
    return nums


def patient_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("patient_"):
            return part
    return ""


def scan_key(struct_path: Path, rtstruct) -> tuple[str, str, str]:
    ct_headers = choose_ct_series(
        read_ct_headers(struct_path.parent),
        structure_frame_uid(rtstruct),
        referenced_image_uids(rtstruct),
    )
    date, time = dicom_date_time(ct_headers)
    return (clean_patient_id(patient_from_path(struct_path)), date, ct_headers[0]["series_uid"])


def count(scope: str, paths: list[Path]) -> None:
    by_category: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    by_category_struct: dict[str, set[str]] = defaultdict(set)
    organ_scans: set[tuple[str, str, str]] = set()
    organ_structs: set[str] = set()

    for path in paths:
        rtstruct = pydicom.dcmread(str(path), force=True, stop_before_pixels=True)
        key = scan_key(path, rtstruct)
        roi_names = roi_number_to_name(rtstruct)
        contour_nums = roi_numbers_with_contours(rtstruct)
        for number, name in roi_names.items():
            if number not in contour_nums:
                continue
            cats = broad_categories(name)
            for cat in cats:
                by_category[cat].add(key)
                by_category_struct[cat].add(str(path))
            if cats & {"Lung", "Heart", "SpinalCord", "Esophagus"}:
                organ_scans.add(key)
                organ_structs.add(str(path))

    print(f"\n=== {scope} contour-capable broad scan counts ===")
    for cat in ["GTV", "CTV", "Lung", "Heart", "SpinalCord", "Esophagus"]:
        print(f"{cat}: scans={len(by_category[cat])}, rtstructs={len(by_category_struct[cat])}")
    print(f"Organ(any Lung/Heart/SpinalCord/Esophagus): scans={len(organ_scans)}, rtstructs={len(organ_structs)}")


def main() -> None:
    count("gtv_cases_only", unique_gtv_structures())
    count("all_rtstructs", all_referenced_structures())


if __name__ == "__main__":
    main()
