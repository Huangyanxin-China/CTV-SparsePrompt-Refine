#!/usr/bin/env python3
import argparse
import json
import os
import shutil
from pathlib import Path

import SimpleITK as sitk
import numpy as np


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        try:
            dst.symlink_to(src)
        except OSError:
            shutil.copy2(src, dst)


def convert_label(src: Path, dst: Path) -> None:
    img = sitk.ReadImage(str(src))
    arr = sitk.GetArrayFromImage(img)
    arr = arr.astype(np.uint8, copy=False)
    arr = arr.copy()
    arr[arr == 5] = 0
    out = sitk.GetImageFromArray(arr)
    out.CopyInformation(img)
    sitk.WriteImage(out, str(dst), useCompression=True)


def convert_split(source: Path, target: Path, split: str) -> tuple[int, int]:
    images_src = source / f"images{split}"
    labels_src = source / f"labels{split}"
    images_dst = target / f"images{split}"
    labels_dst = target / f"labels{split}"
    images_dst.mkdir(parents=True, exist_ok=True)
    labels_dst.mkdir(parents=True, exist_ok=True)

    image_count = 0
    label_count = 0
    for image_file in sorted(images_src.glob("*_0000.nii.gz")):
        link_or_copy(image_file, images_dst / image_file.name)
        image_count += 1

    for label_file in sorted(labels_src.glob("*.nii.gz")):
        convert_label(label_file, labels_dst / label_file.name)
        label_count += 1

    return image_count, label_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a Dataset004-derived OAR-only nnU-Net v2 dataset by setting CTV label 5 to background."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/share3/home/huangyanxin/nnUNet/DATASET/nnUNet_raw/Dataset004_ThoracicOARCTV_OneCaseTrain"),
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("nnunet_runs/raw/Dataset014_ThoracicOAR_Dataset004Split"),
    )
    args = parser.parse_args()

    args.target.mkdir(parents=True, exist_ok=True)
    train_images, train_labels = convert_split(args.source, args.target, "Tr")
    test_images, test_labels = convert_split(args.source, args.target, "Ts")

    dataset_json = {
        "channel_names": {"0": "CT"},
        "labels": {
            "background": 0,
            "lung": 1,
            "heart": 2,
            "spinal": 3,
            "esophagus": 4,
        },
        "numTraining": train_images,
        "file_ending": ".nii.gz",
        "overwrite_image_reader_writer": "SimpleITKIO",
        "name": "Dataset014_ThoracicOAR_Dataset004Split",
    }
    (args.target / "dataset.json").write_text(json.dumps(dataset_json, indent=4) + "\n")

    print(f"target={args.target}")
    print(f"train images={train_images}, train labels={train_labels}")
    print(f"test images={test_images}, test labels={test_labels}")


if __name__ == "__main__":
    main()
