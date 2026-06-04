#!/usr/bin/env python3
"""Build a case-level manifest for the downloaded SegRap2025 LNCTVSeg dataset."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def find_case_ids(image_dir: Path) -> set[str]:
    case_ids: set[str] = set()
    if not image_dir.exists():
        return case_ids
    for path in image_dir.glob("*.nii.gz"):
        name = path.name
        if name.endswith("_0000.nii.gz") or name.endswith("_0001.nii.gz"):
            case_ids.add(name[:-12])
    return case_ids


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("public_data/segrap2025_lnctv/extracted/LNCTVSeg-DataSet"),
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("public_data/segrap2025_lnctv/segrap2025_lnctv_manifest.csv"),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("public_data/segrap2025_lnctv/segrap2025_lnctv_summary.json"),
    )
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    for cohort_dir in sorted(p for p in args.root.iterdir() if p.is_dir()):
        if cohort_dir.name.startswith(".") or "annotation" in cohort_dir.name.lower():
            continue
        for split, image_subdir, label_subdir in [
            ("train", "imagesTr", "labelsTr"),
            ("test", "imagesTs", "labelsTs"),
        ]:
            image_dir = cohort_dir / image_subdir
            label_dir = cohort_dir / label_subdir
            for case_id in sorted(find_case_ids(image_dir)):
                ncct = image_dir / f"{case_id}_0000.nii.gz"
                cect = image_dir / f"{case_id}_0001.nii.gz"
                label = label_dir / f"{case_id}.nii.gz"
                ncct = ncct if ncct.exists() else None
                cect = cect if cect.exists() else None
                label = label if label.exists() else None
                rows.append(
                    {
                        "cohort": cohort_dir.name,
                        "case_id": f"{cohort_dir.name}_{split}_{case_id}",
                        "source_case_id": case_id,
                        "split": split,
                        "ncct_path": str(ncct) if ncct else "",
                        "cect_path": str(cect) if cect else "",
                        "label_path": str(label) if label else "",
                        "has_ncct": str(bool(ncct)).lower(),
                        "has_cect": str(bool(cect)).lower(),
                        "has_label": str(bool(label)).lower(),
                    }
                )

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "root": str(args.root),
        "num_cases": len(rows),
        "num_labeled_cases": sum(row["has_label"] == "true" for row in rows),
        "num_paired_ncct_cect_cases": sum(
            row["has_ncct"] == "true" and row["has_cect"] == "true" for row in rows
        ),
        "num_ncct_only_cases": sum(
            row["has_ncct"] == "true" and row["has_cect"] == "false" for row in rows
        ),
        "num_cect_only_cases": sum(
            row["has_ncct"] == "false" and row["has_cect"] == "true" for row in rows
        ),
        "cohorts": {},
    }
    for cohort in sorted({row["cohort"] for row in rows}):
        cohort_rows = [row for row in rows if row["cohort"] == cohort]
        summary["cohorts"][cohort] = {
            "cases": len(cohort_rows),
            "labeled_cases": sum(row["has_label"] == "true" for row in cohort_rows),
            "paired_ncct_cect_cases": sum(
                row["has_ncct"] == "true" and row["has_cect"] == "true" for row in cohort_rows
            ),
            "ncct_only_cases": sum(
                row["has_ncct"] == "true" and row["has_cect"] == "false" for row in cohort_rows
            ),
            "cect_only_cases": sum(
                row["has_ncct"] == "false" and row["has_cect"] == "true" for row in cohort_rows
            ),
        }
    with args.out_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
