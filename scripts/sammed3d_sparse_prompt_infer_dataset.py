#!/usr/bin/env python3
import argparse
import csv
import os
import os.path as osp
import sys
from glob import glob

import numpy as np
import SimpleITK as sitk
from tqdm import tqdm


DEFAULT_CLASSES = {
    "ctv": [1],
    "oar": [1, 2, 3, 4],
}

CLASS_NAMES = {
    "ctv": ["ctv"],
    "oar": ["lung", "heart", "spinal", "esophagus"],
}


def read_image(path):
    image = sitk.ReadImage(path)
    arr = sitk.GetArrayFromImage(image)
    return arr, image


def write_like(arr, ref_image, path):
    out = sitk.GetImageFromArray(arr.astype(np.uint8))
    out.CopyInformation(ref_image)
    sitk.WriteImage(out, path)


def case_names_from_img_dir(img_dir):
    names = []
    for path in sorted(glob(osp.join(img_dir, "*.nii.gz"))):
        name = osp.basename(path).replace(".nii.gz", "")
        if name.endswith("_0000"):
            name = name[:-5]
        names.append(name)
    return names


def resolve_image_path(img_dir, case):
    path = osp.join(img_dir, f"{case}_0000.nii.gz")
    if osp.exists(path):
        return path
    path = osp.join(img_dir, f"{case}.nii.gz")
    if osp.exists(path):
        return path
    raise FileNotFoundError(path)


def fill_to_k(selected, available, k):
    selected = sorted(set(int(v) for v in selected))
    available = np.asarray(sorted(set(int(v) for v in available)), dtype=int)
    if len(selected) >= k:
        return np.asarray(selected[:k], dtype=int)
    while len(selected) < k and len(selected) < len(available):
        if not selected:
            selected.append(int(available[len(available) // 2]))
            continue
        dist = np.min(np.abs(available[:, None] - np.asarray(selected)[None, :]), axis=1)
        order = np.argsort(dist)[::-1]
        for idx in order:
            cand = int(available[idx])
            if cand not in selected:
                selected.append(cand)
                break
        else:
            break
    return np.asarray(sorted(set(selected)), dtype=int)


def select_sparse_slices(gt, cls, k, strategy):
    z_available = np.where((gt == cls).reshape(gt.shape[0], -1).any(axis=1))[0]
    if z_available.size == 0:
        return np.asarray([], dtype=int)
    if z_available.size <= k:
        return z_available.astype(int)

    if strategy == "even_nonempty":
        idx = np.round(np.linspace(0, z_available.size - 1, k)).astype(int)
        return fill_to_k(z_available[idx], z_available, k)

    if strategy == "max_area_anchors":
        areas = (gt == cls).reshape(gt.shape[0], -1).sum(axis=1)
        first = int(z_available[0])
        last = int(z_available[-1])
        center = int(np.argmax(areas))
        anchors = [first, center, last]
        return fill_to_k(anchors, z_available, k)

    raise ValueError(f"Unsupported slice selection strategy: {strategy}")


def make_sparse_prompt(gt, classes, k, strategy):
    prompt = np.zeros_like(gt, dtype=np.uint8)
    selections = {}
    for cls in classes:
        selected_z = select_sparse_slices(gt, int(cls), int(k), strategy)
        selections[int(cls)] = selected_z.tolist()
        for z in selected_z:
            prompt[int(z)][gt[int(z)] == int(cls)] = int(cls)
    return prompt, selections


def run_evaluation(args, classes, class_names):
    out_json = args.output_json or osp.join(args.out_dir, "metrics_summary.json")
    out_csv = args.output_csv or osp.join(args.out_dir, "metrics_per_case.csv")
    cmd = [
        sys.executable,
        osp.join(args.project_root, "scripts", "evaluate_segmentation_folder.py"),
        "--gt_dir", args.gt_dir,
        "--pred_dir", args.out_dir,
        "--classes", *[str(c) for c in classes],
        "--class_names", *class_names,
        "--output_csv", out_csv,
        "--output_json", out_json,
    ]
    print("Running global evaluation:", " ".join(cmd))
    import subprocess

    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "SAM-Med3D sparse-slice prompt inference. The complete GT is used only "
            "to simulate K annotated 2D prompt slices and for final global evaluation."
        )
    )
    parser.add_argument("--repo", default="/share3/home/huangyanxin/SAM-Med3D-main")
    parser.add_argument("--project_root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    parser.add_argument("--img_dir", required=True)
    parser.add_argument("--gt_dir", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--task", choices=["ctv", "oar"], default="ctv")
    parser.add_argument("--classes", nargs="+", type=int, default=None)
    parser.add_argument("--k", type=int, default=7)
    parser.add_argument("--selection", choices=["even_nonempty", "max_area_anchors"], default="even_nonempty")
    parser.add_argument("--num_clicks", type=int, default=7)
    parser.add_argument("--crop_size", type=int, default=128)
    parser.add_argument("--target_spacing", nargs=3, type=float, default=[1.5, 1.5, 1.5])
    parser.add_argument("--output_csv", default=None)
    parser.add_argument("--output_json", default=None)
    parser.add_argument("--selection_csv", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry_run", action="store_true")
    args = parser.parse_args()

    classes = args.classes or DEFAULT_CLASSES[args.task]
    class_names = [CLASS_NAMES[args.task][DEFAULT_CLASSES[args.task].index(c)] for c in classes]

    repo = os.path.abspath(args.repo)
    sys.path.insert(0, repo)
    from utils.infer_utils import validate_paired_img_gt
    import medim

    os.makedirs(args.out_dir, exist_ok=True)
    prompt_dir = osp.join(args.out_dir, "_sparse_prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    selection_csv = args.selection_csv or osp.join(args.out_dir, "sparse_prompt_slices.csv")
    cases = case_names_from_img_dir(args.img_dir)
    if args.limit > 0:
        cases = cases[: args.limit]

    model = None
    if not args.dry_run:
        model = medim.create_model("SAM-Med3D", pretrained=True, checkpoint_path=args.ckpt)

    selection_rows = []
    for case in tqdm(cases, desc=f"SAM-Med3D sparse prompt {args.task}"):
        img_path = resolve_image_path(args.img_dir, case)
        gt_path = osp.join(args.gt_dir, f"{case}.nii.gz")
        if not osp.exists(gt_path):
            raise FileNotFoundError(gt_path)

        gt, ref = read_image(gt_path)
        prompt, selections = make_sparse_prompt(gt, classes, args.k, args.selection)
        prompt_path = osp.join(prompt_dir, f"{case}.nii.gz")
        write_like(prompt, ref, prompt_path)

        for cls, selected in selections.items():
            selection_rows.append(
                {
                    "case": case,
                    "class_id": cls,
                    "k_requested": int(args.k),
                    "n_selected": len(selected),
                    "selection": args.selection,
                    "selected_z": ";".join(str(z) for z in selected),
                    "prompt_voxels": int((prompt == cls).sum()),
                    "gt_voxels": int((gt == cls).sum()),
                    "prompt_path": prompt_path,
                }
            )

        if args.dry_run:
            continue

        out_path = osp.join(args.out_dir, f"{case}.nii.gz")
        validate_paired_img_gt(
            model,
            img_path,
            prompt_path,
            out_path,
            num_clicks=args.num_clicks,
            crop_size=args.crop_size,
            target_spacing=tuple(args.target_spacing),
        )

    os.makedirs(osp.dirname(selection_csv), exist_ok=True)
    with open(selection_csv, "w", newline="") as f:
        fieldnames = [
            "case",
            "class_id",
            "k_requested",
            "n_selected",
            "selection",
            "selected_z",
            "prompt_voxels",
            "gt_voxels",
            "prompt_path",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selection_rows)
    print("Wrote", selection_csv)

    if not args.dry_run:
        run_evaluation(args, classes, class_names)


if __name__ == "__main__":
    main()
