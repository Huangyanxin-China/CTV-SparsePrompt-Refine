#!/usr/bin/env python3
"""
Create an nnU-Net-like multimodal CTV dataset from a downloaded LUND-PROBE tree.

Expected input layout per case:
    <raw_root>/<case>/MR_StorT2/image.nii.gz
    <raw_root>/<case>/MR_StorT2/mask_CTVT_427.nii.gz
    <raw_root>/<case>/MR_StorT2/mask_Rectum.nii.gz
    <raw_root>/<case>/MR_StorT2/mask_Bladder.nii.gz
    <raw_root>/<case>/MR_StorT2/mask_FemoralHead_L.nii.gz
    <raw_root>/<case>/MR_StorT2/mask_FemoralHead_R.nii.gz
    <raw_root>/<case>/sCT/image_reg2MRI.nii.gz

Output:
    <out_root>/images/<case>_0000.nii.gz  # MRI
    <out_root>/images/<case>_0001.nii.gz  # registered sCT
    <out_root>/labels/<case>.nii.gz       # combined labels
    <out_root>/dataset_lund_probe_multimodal_ctv.json
    <out_root>/case_index.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import numpy as np
import SimpleITK as sitk


LABELS = {
    "background": 0,
    "ctv": 1,
    "rectum": 2,
    "bladder": 3,
    "femoral_head_l": 4,
    "femoral_head_r": 5,
}


MASK_FILES = [
    ("ctv", "mask_CTVT_427.nii.gz"),
    ("rectum", "mask_Rectum.nii.gz"),
    ("bladder", "mask_Bladder.nii.gz"),
    ("femoral_head_l", "mask_FemoralHead_L.nii.gz"),
    ("femoral_head_r", "mask_FemoralHead_R.nii.gz"),
]


def copy_or_link(src: Path, dst: Path, mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "symlink":
        dst.symlink_to(src.resolve())
    elif mode == "copy":
        shutil.copy2(src, dst)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def same_geometry(a: sitk.Image, b: sitk.Image) -> bool:
    return (
        a.GetSize() == b.GetSize()
        and np.allclose(a.GetSpacing(), b.GetSpacing())
        and np.allclose(a.GetOrigin(), b.GetOrigin())
        and np.allclose(a.GetDirection(), b.GetDirection())
    )


def combine_masks(case_dir: Path, ref_img: sitk.Image) -> tuple[sitk.Image, dict[str, bool]]:
    label_arr = np.zeros(sitk.GetArrayFromImage(ref_img).shape, dtype=np.uint8)
    present: dict[str, bool] = {}

    mri_dir = case_dir / "MR_StorT2"
    for label_name, filename in MASK_FILES:
        path = mri_dir / filename
        present[label_name] = path.exists()
        if not path.exists():
            continue
        mask = sitk.ReadImage(str(path))
        if not same_geometry(ref_img, mask):
            raise RuntimeError(f"Geometry mismatch for {path}")
        arr = sitk.GetArrayFromImage(mask) > 0
        label_arr[arr] = LABELS[label_name]

    out = sitk.GetImageFromArray(label_arr)
    out.CopyInformation(ref_img)
    return out, present


def find_cases(raw_root: Path) -> list[Path]:
    cases = []
    for case_dir in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        if (case_dir / "MR_StorT2" / "image.nii.gz").exists():
            cases.append(case_dir)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--mode", choices=["symlink", "copy"], default="symlink")
    parser.add_argument("--require-sct", action="store_true")
    args = parser.parse_args()

    raw_root = args.raw_root.resolve()
    out_root = args.out_root.resolve()
    images_dir = out_root / "images"
    labels_dir = out_root / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for case_dir in find_cases(raw_root):
        case_id = case_dir.name
        mri_path = case_dir / "MR_StorT2" / "image.nii.gz"
        sct_path = case_dir / "sCT" / "image_reg2MRI.nii.gz"
        ctv_path = case_dir / "MR_StorT2" / "mask_CTVT_427.nii.gz"

        if not ctv_path.exists():
            rows.append({"case_id": case_id, "status": "skip_missing_ctv"})
            continue
        if args.require_sct and not sct_path.exists():
            rows.append({"case_id": case_id, "status": "skip_missing_sct"})
            continue

        ref_img = sitk.ReadImage(str(mri_path))
        if sct_path.exists():
            sct_img = sitk.ReadImage(str(sct_path))
            if not same_geometry(ref_img, sct_img):
                rows.append({"case_id": case_id, "status": "skip_sct_geometry_mismatch"})
                continue

        label_img, present = combine_masks(case_dir, ref_img)

        copy_or_link(mri_path, images_dir / f"{case_id}_0000.nii.gz", args.mode)
        if sct_path.exists():
            copy_or_link(sct_path, images_dir / f"{case_id}_0001.nii.gz", args.mode)
        sitk.WriteImage(label_img, str(labels_dir / f"{case_id}.nii.gz"))

        row = {
            "case_id": case_id,
            "status": "ok",
            "mri": str(mri_path),
            "sct": str(sct_path) if sct_path.exists() else "",
        }
        row.update({f"has_{k}": int(v) for k, v in present.items()})
        rows.append(row)

    with (out_root / "case_index.csv").open("w", newline="") as f:
        fieldnames = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_cases = [r for r in rows if r.get("status") == "ok"]
    dataset_json = {
        "name": "LUND_PROBE_Multimodal_CTV",
        "channel_names": {"0": "MRI_T2", "1": "sCT_reg2MRI"},
        "labels": {str(v): k for k, v in LABELS.items()},
        "num_cases": len(ok_cases),
        "file_ending": ".nii.gz",
        "source": "LUND-PROBE controlled-access dataset",
    }
    (out_root / "dataset_lund_probe_multimodal_ctv.json").write_text(
        json.dumps(dataset_json, indent=2)
    )
    print(json.dumps({"out_root": str(out_root), "ok_cases": len(ok_cases)}, indent=2))


if __name__ == "__main__":
    main()
