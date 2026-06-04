#!/usr/bin/env python3
"""Check local acquisition status for external multimodal CTV datasets."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def exists_line(path: Path, label: str | None = None) -> str:
    rel = path.relative_to(ROOT) if path.is_absolute() and path.is_relative_to(ROOT) else path
    state = "OK" if path.exists() else "MISSING"
    return f"{state:8} {label or str(rel)}"


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file())


def load_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def print_manifest_summary(name: str, summary_path: Path) -> None:
    summary = load_summary(summary_path)
    if not summary:
        print(f"{name}: manifest summary missing")
        return
    print(f"{name}: {summary.get('patients', '?')} patients, {summary.get('rows', '?')} rows")
    modalities = summary.get("modalities", {})
    if modalities:
        print("  modalities: " + ", ".join(f"{k}={v}" for k, v in sorted(modalities.items())))


def main() -> None:
    print("External multimodal CTV data status")
    print("=" * 43)
    print(f"gen3 command: {shutil.which('gen3') or 'MISSING'}")
    print()

    glis = ROOT / "public_data" / "glis_rt"
    burdenko = ROOT / "public_data" / "burdenko_gbm_progression"
    segrap = ROOT / "public_data" / "segrap2025_lnctv"

    print("SegRap2025 LNCTVSeg")
    archive = segrap / "raw" / "LNCTVSeg-DataSet.zip"
    extracted = segrap / "extracted" / "LNCTVSeg-DataSet"
    if archive.exists():
        print(exists_line(archive))
    elif extracted.exists():
        print(f"{'CLEANED':8} public_data/segrap2025_lnctv/raw/LNCTVSeg-DataSet.zip")
    else:
        print(exists_line(archive))
    print(exists_line(segrap / "extracted" / "LNCTVSeg-DataSet"))
    print(f"{'FILES':8} extracted NIfTI files: {len(list((segrap / 'extracted' / 'LNCTVSeg-DataSet').rglob('*.nii.gz'))) if (segrap / 'extracted' / 'LNCTVSeg-DataSet').exists() else 0}")
    print(exists_line(segrap / "segrap2025_lnctv_manifest.csv"))
    print(exists_line(segrap / "segrap2025_lnctv_summary.json"))
    print()

    print("GLIS-RT")
    print(exists_line(glis / "GC_manifest_GLIS-RT_20260326.csv"))
    print(exists_line(glis / "manifests" / "glis_rt_all_gen3_manifest.json"))
    print(exists_line(glis / "raw_zips"))
    print(f"{'FILES':8} raw_zips files: {count_files(glis / 'raw_zips')}")
    print_manifest_summary("  summary", glis / "manifests" / "manifest_summary.json")
    print()

    print("Burdenko-GBM-Progression")
    print(exists_line(burdenko / "GC_manifest_Burdenko-GBM-Progression_20260326.csv"))
    print(exists_line(burdenko / "manifests" / "burdenko_gbm_all_gen3_manifest.json"))
    print(exists_line(burdenko / "raw_zips"))
    print(f"{'FILES':8} raw_zips files: {count_files(burdenko / 'raw_zips')}")
    print_manifest_summary("  summary", burdenko / "manifests" / "manifest_summary.json")
    print()

    print("Current blocker")
    if (segrap / "extracted" / "LNCTVSeg-DataSet").exists():
        print("SegRap2025 LNCTVSeg is present and can be used for open public CTV validation.")
        if count_files(glis / "raw_zips") == 0 and count_files(burdenko / "raw_zips") == 0:
            print("Stricter CT+MR/MRI+sCT datasets still require controlled-access approval/credentials.")
    elif count_files(glis / "raw_zips") == 0 and count_files(burdenko / "raw_zips") == 0:
        print("Raw imaging is not present. Controlled-access approval/credentials are still required.")
    else:
        print("At least one raw dataset directory has files. Proceed to conversion/validation checks.")


if __name__ == "__main__":
    main()
