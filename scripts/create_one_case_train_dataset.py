#!/usr/bin/env python3
"""Create a renamed nnUNet dataset with one training case per patient."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path


IMAGE_RE = re.compile(r"^patient_(P\d+)_Lung_CT_(\d{8})_0000\.nii\.gz$")


def parse_image_name(path: Path) -> tuple[str, str]:
    match = IMAGE_RE.match(path.name)
    if match is None:
        raise ValueError(f"Cannot parse image name: {path.name}")
    return match.group(1), match.group(2)


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def collect_cases(source_dir: Path) -> dict[tuple[str, str], dict[str, Path]]:
    cases: dict[tuple[str, str], dict[str, Path]] = {}
    for split in ("Tr", "Ts"):
        image_dir = source_dir / f"images{split}"
        label_dir = source_dir / f"labels{split}"
        if not image_dir.exists():
            continue
        for image_path in sorted(image_dir.glob("*.nii.gz")):
            patient_id, ct_date = parse_image_name(image_path)
            label_name = image_path.name.replace("_0000.nii.gz", ".nii.gz")
            label_path = label_dir / label_name
            if not label_path.exists():
                raise FileNotFoundError(f"Missing label for {image_path}: {label_path}")

            key = (patient_id, ct_date)
            # Prefer the training copy when the same case exists in both source splits.
            if key in cases and cases[key]["source_split"] == "Tr":
                continue
            cases[key] = {
                "image": image_path,
                "label": label_path,
                "source_split": split,
            }
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source_dir",
        default="/share3/home/huangyanxin/nnUNet/DATASET/nnUNet_raw/Dataset002_LungOrgans",
        type=Path,
    )
    parser.add_argument(
        "--target_dir",
        default="/share3/home/huangyanxin/nnUNet/DATASET/nnUNet_raw/Dataset004_ThoracicOARCTV_OneCaseTrain",
        type=Path,
    )
    parser.add_argument(
        "--train_case_policy",
        choices=("earliest", "latest"),
        default="earliest",
        help="Which dated case to place in training for each patient.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source_dir = args.source_dir
    target_dir = args.target_dir
    if not source_dir.exists():
        raise FileNotFoundError(source_dir)
    if target_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"{target_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(target_dir)

    cases = collect_cases(source_dir)
    by_patient: dict[str, list[str]] = defaultdict(list)
    for patient_id, ct_date in cases:
        by_patient[patient_id].append(ct_date)

    split_rows = []
    for patient_id in sorted(by_patient):
        dates = sorted(by_patient[patient_id])
        train_date = dates[0] if args.train_case_policy == "earliest" else dates[-1]
        for ct_date in dates:
            split = "train" if ct_date == train_date else "test"
            src = cases[(patient_id, ct_date)]
            case_id = f"{patient_id}_CT{ct_date}"
            image_name = f"{case_id}_0000.nii.gz"
            label_name = f"{case_id}.nii.gz"
            if split == "train":
                image_dst = target_dir / "imagesTr" / image_name
                label_dst = target_dir / "labelsTr" / label_name
            else:
                image_dst = target_dir / "imagesTs" / image_name
                label_dst = target_dir / "labelsTs" / label_name
            link_or_copy(src["image"], image_dst)
            link_or_copy(src["label"], label_dst)
            split_rows.append(
                {
                    "case_id": case_id,
                    "patient_id": patient_id,
                    "ct_date": ct_date,
                    "split": split,
                    "source_split": src["source_split"],
                    "source_image": str(src["image"]),
                    "source_label": str(src["label"]),
                    "image": str(image_dst.relative_to(target_dir)),
                    "label": str(label_dst.relative_to(target_dir)),
                }
            )

    source_json = source_dir / "dataset.json"
    with source_json.open() as f:
        dataset_json = json.load(f)
    dataset_json["name"] = target_dir.name
    dataset_json["numTraining"] = sum(row["split"] == "train" for row in split_rows)
    dataset_json["file_ending"] = dataset_json.get("file_ending", ".nii.gz")
    dataset_json.setdefault("overwrite_image_reader_writer", "SimpleITKIO")
    # Keep the source label definition unchanged to match existing nnUNet setup.
    dataset_json.pop("training", None)
    with (target_dir / "dataset.json").open("w") as f:
        json.dump(dataset_json, f, indent=4)
        f.write("\n")

    with (target_dir / "case_split.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case_id",
                "patient_id",
                "ct_date",
                "split",
                "source_split",
                "source_image",
                "source_label",
                "image",
                "label",
            ],
        )
        writer.writeheader()
        writer.writerows(split_rows)

    print(f"Created: {target_dir}")
    print(f"Unique cases: {len(cases)}")
    print(f"Patients: {len(by_patient)}")
    print(f"Train cases: {sum(row['split'] == 'train' for row in split_rows)}")
    print(f"Test cases: {sum(row['split'] == 'test' for row in split_rows)}")


if __name__ == "__main__":
    main()
