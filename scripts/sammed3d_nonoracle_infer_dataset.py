#!/usr/bin/env python3
import argparse
import os
import os.path as osp
import subprocess
import sys
from glob import glob

import numpy as np
import SimpleITK as sitk
from tqdm import tqdm

try:
    from scipy import ndimage
except Exception:
    ndimage = None


DEFAULT_CLASSES = {
    "ctv": [1],
    "oar": [1, 2, 3, 4],
}

CLASS_NAMES = {
    "ctv": ["ctv"],
    "oar": ["lung", "heart", "spinal", "esophagus"],
}


def read_ct(path):
    image = sitk.ReadImage(path)
    arr = sitk.GetArrayFromImage(image).astype(np.float32)
    return arr, image


def write_like(arr, ref_image, path):
    out = sitk.GetImageFromArray(arr.astype(np.uint8))
    out.CopyInformation(ref_image)
    sitk.WriteImage(out, path)


def largest_components(mask, keep=1, min_size=1000):
    if ndimage is None:
        return mask
    labeled, n = ndimage.label(mask)
    if n == 0:
        return mask
    counts = np.bincount(labeled.ravel())
    counts[0] = 0
    keep_labels = [i for i in counts.argsort()[::-1][:keep] if counts[i] >= min_size]
    if not keep_labels:
        return mask
    return np.isin(labeled, keep_labels)


def body_mask_from_ct(ct):
    body = ct > -600
    if ndimage is not None:
        body = ndimage.binary_fill_holes(body)
        body = largest_components(body, keep=1, min_size=10000)
    return body


def bbox_from_mask(mask):
    pts = np.argwhere(mask)
    if pts.size == 0:
        shape = np.asarray(mask.shape)
        return np.zeros(3, dtype=int), shape
    return pts.min(axis=0), pts.max(axis=0) + 1


def box_mask(shape, bbox_min, bbox_max, frac_box):
    bbox_min = np.asarray(bbox_min, dtype=float)
    bbox_max = np.asarray(bbox_max, dtype=float)
    size = np.maximum(bbox_max - bbox_min, 1)
    f = np.asarray(frac_box, dtype=float)
    lo = np.floor(bbox_min + f[[0, 2, 4]] * size).astype(int)
    hi = np.ceil(bbox_min + f[[1, 3, 5]] * size).astype(int)
    lo = np.maximum(lo, 0)
    hi = np.minimum(np.maximum(hi, lo + 1), np.asarray(shape))
    mask = np.zeros(shape, dtype=bool)
    mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = True
    return mask


def prompt_from_ct(ct, task, classes, mode):
    prompt = np.zeros(ct.shape, dtype=np.uint8)
    body = body_mask_from_ct(ct)
    bmin, bmax = bbox_from_mask(body)

    if task == "ctv":
        # Coarse mediastinal/thoracic search region. This is intentionally not
        # derived from GT and should be treated only as an automatic prompt prior.
        prompt[box_mask(ct.shape, bmin, bmax, (0.25, 0.78, 0.30, 0.76, 0.30, 0.70))] = 1
        return prompt

    if task != "oar":
        raise ValueError(f"Unsupported task: {task}")

    for cls in classes:
        cls_mask = np.zeros(ct.shape, dtype=bool)
        if cls == 1 and mode == "ct_heuristic":
            lung = (ct < -400) & body
            cls_mask = largest_components(lung, keep=2, min_size=5000)
            if cls_mask.sum() < 5000:
                cls_mask = box_mask(ct.shape, bmin, bmax, (0.10, 0.90, 0.12, 0.86, 0.10, 0.90))
        elif cls == 1:
            cls_mask = box_mask(ct.shape, bmin, bmax, (0.10, 0.90, 0.12, 0.86, 0.10, 0.90))
        elif cls == 2:
            cls_mask = box_mask(ct.shape, bmin, bmax, (0.38, 0.78, 0.38, 0.76, 0.34, 0.66))
        elif cls == 3:
            cls_mask = box_mask(ct.shape, bmin, bmax, (0.08, 0.92, 0.60, 0.88, 0.44, 0.56))
        elif cls == 4:
            cls_mask = box_mask(ct.shape, bmin, bmax, (0.18, 0.88, 0.40, 0.70, 0.45, 0.56))
        else:
            raise ValueError(f"Unsupported OAR class: {cls}")
        prompt[cls_mask] = cls
    return prompt


def resolve_image_path(img_dir, case):
    candidates = [
        osp.join(img_dir, f"{case}_0000.nii.gz"),
        osp.join(img_dir, f"{case}.nii.gz"),
    ]
    for path in candidates:
        if osp.exists(path):
            return path
    raise FileNotFoundError(candidates[0])


def case_names_from_img_dir(img_dir):
    names = []
    for path in sorted(glob(osp.join(img_dir, "*.nii.gz"))):
        name = osp.basename(path).replace(".nii.gz", "")
        if name.endswith("_0000"):
            name = name[:-5]
        names.append(name)
    return names


def run_evaluation(args, classes, class_names):
    if not args.gt_dir:
        return
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
    print("Running evaluation:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Non-oracle SAM-Med3D inference. Test GT is not used for prompt generation or ROI cropping."
    )
    parser.add_argument("--repo", default="/share3/home/huangyanxin/SAM-Med3D-main")
    parser.add_argument("--project_root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    parser.add_argument("--img_dir", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--task", choices=["ctv", "oar"], required=True)
    parser.add_argument("--classes", nargs="+", type=int, default=None)
    parser.add_argument("--prompt_mode", choices=["ct_heuristic", "fixed_boxes"], default="ct_heuristic")
    parser.add_argument("--num_clicks", type=int, default=1)
    parser.add_argument("--crop_size", type=int, default=128)
    parser.add_argument("--target_spacing", nargs=3, type=float, default=[1.5, 1.5, 1.5])
    parser.add_argument("--gt_dir", default=None, help="Only used for final evaluation, never for inference.")
    parser.add_argument("--output_csv", default=None)
    parser.add_argument("--output_json", default=None)
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
    prompt_dir = osp.join(args.out_dir, "_nonoracle_prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    cases = case_names_from_img_dir(args.img_dir)
    if args.limit > 0:
        cases = cases[:args.limit]

    model = None
    if not args.dry_run:
        model = medim.create_model("SAM-Med3D", pretrained=True, checkpoint_path=args.ckpt)

    for case in tqdm(cases, desc=f"SAM-Med3D non-oracle {args.task}"):
        img_path = resolve_image_path(args.img_dir, case)
        ct, ref = read_ct(img_path)
        prompt = prompt_from_ct(ct, args.task, classes, args.prompt_mode)
        prompt_path = osp.join(prompt_dir, f"{case}.nii.gz")
        write_like(prompt, ref, prompt_path)

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

    run_evaluation(args, classes, class_names)


if __name__ == "__main__":
    main()
