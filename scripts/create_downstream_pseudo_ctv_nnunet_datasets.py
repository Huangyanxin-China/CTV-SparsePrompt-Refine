#!/usr/bin/env python3
"""Create downstream CTV nnU-Net datasets with pseudo-label supervision.

The test labels remain the complete expert CTV labels. Only labelsTr changes:
linear interpolation, SDF core, or the train-calibrated support-intersection rule.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_sparse_prompt_core_envelope_workflow as wf
import run_k7_preprocess_variant_screen as screen
from run_traditional_linear_mask_interpolation_baseline import linear_mask_interpolation


DATASETS = {
    "linear": (16, "Dataset016_CTVLinearPseudoK7"),
    "sdf_core": (17, "Dataset017_CTVSDFCorePseudoK7"),
    "ours": (18, "Dataset018_CTVOursSupportIntersectionK7"),
}


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        try:
            dst.symlink_to(src)
        except OSError:
            shutil.copy2(src, dst)


def read_mask(path: Path) -> tuple[np.ndarray, sitk.Image]:
    image = sitk.ReadImage(str(path))
    return sitk.GetArrayFromImage(image) > 0, image


def write_mask(mask: np.ndarray, ref: sitk.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = sitk.GetImageFromArray(mask.astype(np.uint8))
    out.CopyInformation(ref)
    sitk.WriteImage(out, str(path), useCompression=True)


def case_id_from_label(path: Path) -> str:
    return path.name.replace(".nii.gz", "")


def build_predictions(gt: np.ndarray, gt_img: sitk.Image, case_id: str, k: int, strategy: str, profile: str) -> dict[str, np.ndarray]:
    selected_z = wf.select_sparse_slices(gt, int(k), strategy, case_id)
    prompt = wf.make_prompt(gt, selected_z)

    linear = linear_mask_interpolation(prompt).astype(bool)
    linear[prompt] = True

    oar = np.zeros_like(gt, dtype=np.uint8)
    methods, support, _ = wf.build_methods(prompt, selected_z, gt_img.GetSpacing(), oar, profile)
    core = methods["core_only"].astype(bool)

    support_100 = screen.support_mask(support, 1.0, prompt)
    inter = (linear & core)
    inter[prompt] = True

    feature = float(core.sum() / max(int(methods["sdf_base"].astype(bool).sum()), 1))
    # This threshold is the train-calibrated rule saved in
    # results/data_preprocess_variant_screen_k7_20260602/summary.json.
    ours = inter if feature < 0.990869732950405 else support_100
    ours[prompt] = True

    return {
        "linear": linear,
        "sdf_core": core,
        "ours": ours.astype(bool),
    }


def write_dataset_json(path: Path, name: str, num_training: int) -> None:
    payload = {
        "channel_names": {"0": "CT"},
        "labels": {"background": 0, "ctv": 1},
        "numTraining": int(num_training),
        "file_ending": ".nii.gz",
        "overwrite_image_reader_writer": "SimpleITKIO",
        "name": name,
    }
    path.write_text(json.dumps(payload, indent=4) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "nnunet_runs/raw/Dataset015_CTV_Dataset004Split")
    parser.add_argument("--raw_root", type=Path, default=ROOT / "nnunet_runs/raw")
    parser.add_argument("--k", type=int, default=7)
    parser.add_argument("--strategy", default="even_nonempty")
    parser.add_argument("--profile", default="current")
    args = parser.parse_args()

    label_files = sorted((args.source / "labelsTr").glob("*.nii.gz"))
    if not label_files:
        raise SystemExit(f"No training labels found in {args.source / 'labelsTr'}")

    for _, dataset_name in DATASETS.values():
        target = args.raw_root / dataset_name
        for split in ("Tr", "Ts"):
            for sub in (f"images{split}", f"labels{split}"):
                (target / sub).mkdir(parents=True, exist_ok=True)

        for image_path in sorted((args.source / "imagesTr").glob("*_0000.nii.gz")):
            link_or_copy(image_path, target / "imagesTr" / image_path.name)
        for image_path in sorted((args.source / "imagesTs").glob("*_0000.nii.gz")):
            link_or_copy(image_path, target / "imagesTs" / image_path.name)
        for label_path in sorted((args.source / "labelsTs").glob("*.nii.gz")):
            link_or_copy(label_path, target / "labelsTs" / label_path.name)

    manifest = []
    for label_path in label_files:
        case_id = case_id_from_label(label_path)
        gt, gt_img = read_mask(label_path)
        preds = build_predictions(gt, gt_img, case_id, args.k, args.strategy, args.profile)
        for method, pred in preds.items():
            _, dataset_name = DATASETS[method]
            out_path = args.raw_root / dataset_name / "labelsTr" / label_path.name
            write_mask(pred, gt_img, out_path)
            manifest.append(
                {
                    "dataset": dataset_name,
                    "method": method,
                    "case": case_id,
                    "voxels": int(pred.sum()),
                    "dice_to_gt": wf.dice_score(pred, gt),
                }
            )
        print(f"generated {case_id}", flush=True)

    for method, (dataset_id, dataset_name) in DATASETS.items():
        target = args.raw_root / dataset_name
        write_dataset_json(target / "dataset.json", dataset_name, len(label_files))
        rows = [row for row in manifest if row["method"] == method]
        dice = np.asarray([float(row["dice_to_gt"]) for row in rows], dtype=float)
        summary = {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "method": method,
            "num_training": len(rows),
            "train_pseudo_dice_to_gt_mean": float(dice.mean()),
            "train_pseudo_dice_to_gt_std": float(dice.std()),
        }
        (target / "pseudo_label_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
