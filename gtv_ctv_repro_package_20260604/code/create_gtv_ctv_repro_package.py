from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NNUNET_ROOT = ROOT / "nnUNet_raw_GTV_CTV_Organ"
CTV_DIR = NNUNET_ROOT / "Dataset502_ChestCTV"
GTV_DIR = NNUNET_ROOT / "Dataset503_ChestGTV"
VIS_OUT = ROOT / "outputs" / "gtv_ctv_target_visualization"
STATS_CSV = VIS_OUT / "gtv_ctv_both_cases_stats.csv"


ROOT_SCRIPTS = [
    "visualize_gtv_ctv_targets.py",
    "export_gtv_rtstruct_masks.py",
    "prepare_nnunet_datasets.py",
    "scan_gtv_cases.py",
    "inventory_rtstruct_rois.py",
    "rescreen_broad_labels.py",
    "count_broad_scan_cases.py",
]

RESOURCE_FILES = [
    "gtv_cases.csv",
    "roi_inventory.csv",
    "broad_label_rescreen.csv",
    "organ_roi_audit_summary.json",
    "organ_roi_audit_matches.csv",
    "organ_roi_near_misses.csv",
    "chest_organ_roi_audit_report.pptx",
]


def unique_package_dir(base_name: str) -> Path:
    base = ROOT / base_name
    if not base.exists():
        return base
    for idx in range(1, 100):
        candidate = ROOT / f"{base_name}_{idx:02d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique package directory for {base_name}")


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    for path in src.rglob("*"):
        if path.is_file():
            copy_file(path, dst / path.relative_to(src))


def cases_with_ctv_and_gtv() -> list[str]:
    if STATS_CSV.exists():
        with STATS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            return sorted({row["case_id"] for row in csv.DictReader(f) if row.get("case_id")})
    ctv_cases = {p.name[:-7] for p in (CTV_DIR / "labelsTr").glob("*.nii.gz")}
    gtv_cases = {p.name[:-7] for p in (GTV_DIR / "labelsTr").glob("*.nii.gz")}
    return sorted(ctv_cases & gtv_cases)


def write_dataset_json(path: Path, label_name: str, count: int) -> None:
    payload = {
        "channel_names": {"0": "CT"},
        "labels": {"background": 0, label_name: 1},
        "numTraining": count,
        "file_ending": ".nii.gz",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def copy_subset_nnunet(package_dir: Path, cases: list[str]) -> None:
    target_root = package_dir / "nnUNet_raw_GTV_CTV_Organ"
    for case in cases:
        for dataset_name, source_dir in [
            ("Dataset502_ChestCTV", CTV_DIR),
            ("Dataset503_ChestGTV", GTV_DIR),
        ]:
            dataset_dst = target_root / dataset_name
            copy_file(source_dir / "imagesTr" / f"{case}_0000.nii.gz", dataset_dst / "imagesTr" / f"{case}_0000.nii.gz")
            copy_file(source_dir / "labelsTr" / f"{case}.nii.gz", dataset_dst / "labelsTr" / f"{case}.nii.gz")

    write_dataset_json(target_root / "Dataset502_ChestCTV" / "dataset.json", "CTV", len(cases))
    write_dataset_json(target_root / "Dataset503_ChestGTV" / "dataset.json", "GTV", len(cases))

    manifest = NNUNET_ROOT / "nnunet_export_manifest.csv"
    if manifest.exists():
        with manifest.open("r", encoding="utf-8-sig", newline="") as f:
            rows = [row for row in csv.DictReader(f) if row.get("case_id") in cases and row.get("task") in {"CTV", "GTV"}]
            fieldnames = list(rows[0].keys()) if rows else []
        if rows:
            out = target_root / "nnunet_export_manifest.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)


def write_requirements(package_dir: Path) -> None:
    text = "\n".join(
        [
            "numpy",
            "nibabel",
            "matplotlib",
            "scikit-image",
            "pydicom",
            "",
        ]
    )
    (package_dir / "requirements.txt").write_text(text, encoding="utf-8")


def write_run_scripts(package_dir: Path) -> None:
    sh = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "python3 visualize_gtv_ctv_targets.py",
            "",
        ]
    )
    ps1 = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "python .\\visualize_gtv_ctv_targets.py",
            "",
        ]
    )
    (package_dir / "run_visualization.sh").write_text(sh, encoding="utf-8")
    (package_dir / "run_visualization.ps1").write_text(ps1, encoding="utf-8")


def write_readme(package_dir: Path, cases: list[str]) -> None:
    text = f"""# GTV/CTV Target Visualization Reproduction Package

This package contains the CT images and target masks needed to reproduce the CTV/GTV difference visualization for the {len(cases)} cases that have both CTV and GTV labels.

## Contents

- `visualize_gtv_ctv_targets.py`: main reproduction script.
- `nnUNet_raw_GTV_CTV_Organ/Dataset502_ChestCTV`: CT images and CTV labels for the overlapping cases.
- `nnUNet_raw_GTV_CTV_Organ/Dataset503_ChestGTV`: CT images and GTV labels for the overlapping cases.
- `outputs/gtv_ctv_target_visualization`: generated PNGs, CSV statistics, and summary from the original run.
- `code`: helper scripts used for DICOM/RTSTRUCT scanning, broad ROI-name matching, and nnUNet export.
- `resources`: audit CSV/JSON resources and the earlier organ/ROI audit PPT report.

Original clinical DICOM folders are not included. If you need to rebuild the nnUNet data from DICOM, place the exported clinical folders under this package root and use the scripts in `code` or the matching top-level scripts from the original workspace.

## Reproduce on a Linux server

```bash
cd gtv_ctv_repro_package_20260604
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python visualize_gtv_ctv_targets.py
```

The regenerated outputs will be written to:

```text
outputs/gtv_ctv_target_visualization/
```

Key files after running:

- `outputs/gtv_ctv_target_visualization/gtv_ctv_both_cases_stats.csv`
- `outputs/gtv_ctv_target_visualization/selected_gtv_ctv_difference_contact_sheet.png`
- `outputs/gtv_ctv_target_visualization/all_gtv_ctv_difference_contact_sheet.png`
- `outputs/gtv_ctv_target_visualization/case_pngs/*_gtv_ctv_difference.png`

## Color legend

- Blue: CTV-only region.
- Yellow: CTV and GTV overlap.
- Red: GTV outside CTV.

## Notes

Large red regions may indicate inconsistent target hierarchy, different lesions, multiple exported RTSTRUCTs, or true contour disagreement. These cases should be reviewed manually before using the masks as ground truth.
"""
    (package_dir / "README.md").write_text(text, encoding="utf-8")


def write_package_manifest(package_dir: Path) -> None:
    rows = []
    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            rows.append(
                {
                    "relative_path": str(path.relative_to(package_dir)).replace("\\", "/"),
                    "size_bytes": path.stat().st_size,
                }
            )
    with (package_dir / "PACKAGE_MANIFEST.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["relative_path", "size_bytes"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a portable reproduction package for CTV/GTV visualization.")
    parser.add_argument("--name", default="gtv_ctv_repro_package_20260604", help="Package folder name to create under the current workspace.")
    args = parser.parse_args()

    cases = cases_with_ctv_and_gtv()
    if not cases:
        raise RuntimeError("No cases with both CTV and GTV were found.")

    package_dir = unique_package_dir(args.name)
    package_dir.mkdir(parents=True)

    print(f"Creating package: {package_dir}")
    print(f"Cases with both CTV and GTV: {len(cases)}")

    copy_subset_nnunet(package_dir, cases)

    for script in ROOT_SCRIPTS:
        copy_file(ROOT / script, package_dir / script)
        copy_file(ROOT / script, package_dir / "code" / script)

    for resource in RESOURCE_FILES:
        copy_file(ROOT / resource, package_dir / "resources" / resource)

    copy_file(NNUNET_ROOT / "nnunet_export_manifest.csv", package_dir / "resources" / "full_nnunet_export_manifest.csv")
    copy_tree(VIS_OUT, package_dir / "outputs" / "gtv_ctv_target_visualization")

    report_workspace = ROOT / "outputs" / "manual-20260603-092444" / "presentations" / "organ-roi-audit"
    for extra in ["audit_organ_rois.py", "make_report_assets.py", "build_report_deck.mjs", "report_assets.json"]:
        copy_file(report_workspace / extra, package_dir / "code" / "report" / extra)

    write_requirements(package_dir)
    write_run_scripts(package_dir)
    write_readme(package_dir, cases)
    write_package_manifest(package_dir)

    total_bytes = sum(p.stat().st_size for p in package_dir.rglob("*") if p.is_file())
    print(json.dumps({
        "package_dir": str(package_dir),
        "cases": len(cases),
        "files": sum(1 for p in package_dir.rglob("*") if p.is_file()),
        "size_gb": round(total_bytes / (1024 ** 3), 3),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
