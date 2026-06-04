import argparse
import csv
import json
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
from tqdm import tqdm

try:
    from scipy.ndimage import binary_dilation, binary_erosion
except Exception:
    binary_dilation = None
    binary_erosion = None

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models import create_model
from utils.io import ensure_dir, read_image


def load_rows(metadata_csv, max_cases=0, case_id=None):
    with open(metadata_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    if case_id:
        keep = set(case_id if isinstance(case_id, (list, tuple, set)) else [case_id])
        rows = [row for row in rows if row.get("case_id") in keep]
    if max_cases and max_cases > 0:
        rows = rows[: int(max_cases)]
    return rows


def parse_annotated_z(value):
    return [int(v) for v in str(value).split(";") if str(v).strip() != ""]


def bbox_from_mask(mask, margin=4):
    coords = np.argwhere(mask > 0)
    if coords.size == 0:
        z, y, x = mask.shape
        return np.array([0, 0, 0, x - 1, y - 1, z - 1], dtype=np.float32)
    z0, y0, x0 = coords.min(axis=0)
    z1, y1, x1 = coords.max(axis=0)
    z0 = max(0, z0 - margin)
    y0 = max(0, y0 - margin)
    x0 = max(0, x0 - margin)
    z1 = min(mask.shape[0] - 1, z1 + margin)
    y1 = min(mask.shape[1] - 1, y1 + margin)
    x1 = min(mask.shape[2] - 1, x1 + margin)
    return np.array([x0, y0, z0, x1, y1, z1], dtype=np.float32)


def point_from_mask(mask):
    coords = np.argwhere(mask > 0)
    if coords.size == 0:
        z, y, x = np.array(mask.shape) / 2.0
        return np.array([x, y, z], dtype=np.float32)
    center = coords.mean(axis=0)
    return np.array([center[2], center[1], center[0]], dtype=np.float32)


def supervised_slice_mask(shape, annotated_z):
    out = np.zeros(shape, dtype=np.float32)
    for z in annotated_z:
        if 0 <= int(z) < shape[0]:
            out[int(z)] = 1.0
    return out


def valid_region_from_label(label, avoid_labels=(2, 3, 4)):
    avoid = np.isin(label.astype(np.int16), np.array(avoid_labels, dtype=np.int16))
    return (~avoid).astype(np.float32)


def organ_constraint_masks(label):
    label = label.astype(np.int16)
    lung = (label == 1).astype(np.float32)
    heart = (label == 2).astype(np.float32)
    spinal = (label == 3).astype(np.float32)
    esophagus = (label == 4).astype(np.float32)
    oar = np.maximum.reduce([heart, spinal, esophagus])
    valid = (1.0 - oar).astype(np.float32)
    return {
        "lung": lung,
        "heart": heart,
        "spinal": spinal,
        "esophagus": esophagus,
        "oar": oar.astype(np.float32),
        "valid": valid,
    }


def target_binary_mask(label, target_label=5):
    label = np.asarray(label)
    nonzero_values = set(np.unique(label[label > 0]).astype(int).tolist())
    if not nonzero_values:
        return np.zeros(label.shape, dtype=np.float32)
    if int(target_label) in nonzero_values:
        return (label == int(target_label)).astype(np.float32)
    if nonzero_values.issubset({1}):
        return (label > 0).astype(np.float32)
    return np.zeros(label.shape, dtype=np.float32)


def perturb_center(center_zyx, jitter, shape, rng):
    if jitter <= 0:
        return np.asarray(center_zyx, dtype=np.float32)
    shift = rng.integers(-int(jitter), int(jitter) + 1, size=3)
    center = np.asarray(center_zyx, dtype=np.float32) + shift.astype(np.float32)
    upper = np.maximum(np.asarray(shape, dtype=np.float32) - 1.0, 0.0)
    return np.clip(center, 0.0, upper)


def jitter_point(point_xyz, jitter, shape_zyx, rng):
    if point_xyz is None or jitter <= 0:
        return point_xyz
    point = np.asarray(point_xyz, dtype=np.float32).copy()
    shift_xyz = rng.normal(0.0, float(jitter), size=3).astype(np.float32)
    point += shift_xyz
    d, h, w = shape_zyx
    point[0] = np.clip(point[0], 0, max(w - 1, 0))
    point[1] = np.clip(point[1], 0, max(h - 1, 0))
    point[2] = np.clip(point[2], 0, max(d - 1, 0))
    return point.astype(np.float32)


def morph_binary_mask(mask, radius):
    radius = int(radius)
    if radius == 0:
        return mask.astype(np.float32)
    if binary_dilation is None or binary_erosion is None:
        return mask.astype(np.float32)
    structure = np.ones((3, 3, 3), dtype=bool)
    out = mask > 0
    if radius > 0:
        for _ in range(radius):
            out = binary_dilation(out, structure=structure)
    else:
        for _ in range(abs(radius)):
            out = binary_erosion(out, structure=structure)
    return out.astype(np.float32)


def apply_image_intensity_augmentation(image, args, rng):
    if not getattr(args, "augment", False):
        return image
    out = image.astype(np.float32, copy=True)
    scale_range = float(getattr(args, "intensity_scale_range", 0.0))
    shift_range = float(getattr(args, "intensity_shift_range", 0.0))
    noise_std = float(getattr(args, "gaussian_noise_std", 0.0))
    if scale_range > 0:
        scale = rng.uniform(1.0 - scale_range, 1.0 + scale_range)
        out *= float(scale)
    if shift_range > 0:
        shift = rng.uniform(-shift_range, shift_range)
        out += float(shift)
    if noise_std > 0:
        out += rng.normal(0.0, noise_std, size=out.shape).astype(np.float32)
    return out.astype(np.float32)


def dice_loss_on_mask(prob, target, mask):
    prob = prob * mask
    target = target * mask
    inter = (prob * target).sum()
    denom = prob.sum() + target.sum()
    return 1.0 - (2.0 * inter + 1e-6) / (denom + 1e-6)


def bce_on_mask(logits, target, mask, pos_weight=4.0):
    weight = mask * (1.0 + (float(pos_weight) - 1.0) * target)
    loss = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    return (loss * weight).sum() / (weight.sum() + 1e-6)


def crop_center_from_mask(mask):
    coords = np.argwhere(mask > 0)
    if coords.size == 0:
        return np.array(mask.shape, dtype=np.float32) / 2.0
    return coords.mean(axis=0)


def crop_or_pad_3d(array, center_zyx, patch_size, pad_value=0):
    patch_size = np.array(patch_size, dtype=int)
    center = np.round(np.array(center_zyx, dtype=float)).astype(int)
    start = center - patch_size // 2
    end = start + patch_size

    src_start = np.maximum(start, 0)
    src_end = np.minimum(end, np.array(array.shape, dtype=int))
    dst_start = src_start - start
    dst_end = dst_start + (src_end - src_start)

    patch = np.full(tuple(patch_size.tolist()), pad_value, dtype=array.dtype)
    src_slices = tuple(slice(int(a), int(b)) for a, b in zip(src_start, src_end))
    dst_slices = tuple(slice(int(a), int(b)) for a, b in zip(dst_start, dst_end))
    if np.all(src_end > src_start):
        patch[dst_slices] = array[src_slices]
    return patch, {
        "full_shape": tuple(int(v) for v in array.shape),
        "src_slices": src_slices,
        "dst_slices": dst_slices,
        "start_zyx": tuple(int(v) for v in start),
        "patch_size": tuple(int(v) for v in patch_size),
    }


def paste_patch_3d(patch, crop_info, fill_value=0):
    out = np.full(crop_info["full_shape"], fill_value, dtype=patch.dtype)
    out[crop_info["src_slices"]] = patch[crop_info["dst_slices"]]
    return out


def build_sample(row, args, device, rng=None):
    if rng is None:
        rng = np.random.default_rng(getattr(args, "seed", 42))
    image_np, _ = read_image(row["image_path"])
    pseudo_np, _ = read_image(row["pseudo_label_path"])
    sparse_np, _ = read_image(row["sparse_prompt_path"])
    source_label_np, _ = read_image(row["source_label_path"])
    if not (image_np.shape == pseudo_np.shape == sparse_np.shape == source_label_np.shape):
        raise ValueError(
            "Image, pseudo label, sparse label, and source label must have identical shapes: "
            f"image={image_np.shape}, pseudo={pseudo_np.shape}, sparse={sparse_np.shape}, "
            f"source_label={source_label_np.shape}, case_id={row.get('case_id')}"
        )

    target_label = getattr(args, "target_label", 5)
    sparse_full = target_binary_mask(sparse_np, target_label=target_label)
    pseudo_full = target_binary_mask(pseudo_np, target_label=target_label)
    gt_full = target_binary_mask(source_label_np, target_label=target_label)
    crop_source = getattr(args, "crop_source", "pseudo")
    center_mask = sparse_full if crop_source == "sparse" else pseudo_full
    center_zyx = crop_center_from_mask(center_mask)
    if getattr(args, "augment", False):
        center_zyx = perturb_center(center_zyx, getattr(args, "crop_jitter", 0), image_np.shape, rng)
    patch_size = getattr(args, "patch_size", [128, 128, 128])

    image_np, crop_info = crop_or_pad_3d(image_np.astype(np.float32), center_zyx, patch_size, pad_value=-1000.0)
    sparse, _ = crop_or_pad_3d(sparse_full, center_zyx, patch_size, pad_value=0)
    pseudo, _ = crop_or_pad_3d(pseudo_full, center_zyx, patch_size, pad_value=0)
    gt, _ = crop_or_pad_3d(gt_full, center_zyx, patch_size, pad_value=0)
    source_label_np, _ = crop_or_pad_3d(source_label_np, center_zyx, patch_size, pad_value=0)
    image_np = apply_image_intensity_augmentation(image_np, args, rng)
    constraints = organ_constraint_masks(source_label_np)

    supervision_mode = getattr(args, "supervision_mode", "sparse")
    if supervision_mode == "full_gt":
        target_np = gt
        sup_np = np.ones_like(gt, dtype=np.float32)
    elif supervision_mode == "pseudo":
        target_np = pseudo
        sup_np = np.ones_like(pseudo, dtype=np.float32)
    elif supervision_mode == "sparse":
        target_np = sparse
        annotated_z = np.where(sparse.sum(axis=(1, 2)) > 0)[0].astype(int).tolist()
        sup_np = supervised_slice_mask(sparse.shape, annotated_z)
    else:
        raise ValueError(f"Unknown supervision_mode: {supervision_mode}")

    image = torch.from_numpy(image_np.astype(np.float32))[None, None].to(device)
    target = torch.from_numpy(target_np.astype(np.float32))[None, None].to(device)
    prior = torch.from_numpy(pseudo)[None, None].to(device)
    sparse_target = torch.from_numpy(sparse.astype(np.float32))[None, None].to(device)
    gt_target = torch.from_numpy(gt.astype(np.float32))[None, None].to(device)
    annotated_z = np.where(sparse.sum(axis=(1, 2)) > 0)[0].astype(int).tolist()
    sup = torch.from_numpy(sup_np.astype(np.float32))[None, None].to(device)
    valid = torch.from_numpy(constraints["valid"])[None, None].to(device)
    oar = torch.from_numpy(constraints["oar"])[None, None].to(device)
    lung = torch.from_numpy(constraints["lung"])[None, None].to(device)

    point_box_source = getattr(args, "point_box_source", None) or getattr(args, "prompt_source", "pseudo")
    mask_input_source = getattr(args, "mask_input_source", "pseudo")
    prompt_source = sparse if point_box_source == "sparse" else pseudo
    boxes = None
    points = None
    point_labels = None
    mask_inputs = None
    if "box" in args.prompt_mode:
        box_margin = int(args.box_margin)
        if getattr(args, "augment", False) and getattr(args, "box_margin_jitter", 0) > 0:
            box_margin += int(rng.integers(-int(args.box_margin_jitter), int(args.box_margin_jitter) + 1))
            box_margin = max(0, box_margin)
        boxes = torch.from_numpy(bbox_from_mask(prompt_source, margin=box_margin))[None].to(device)
    if "point" in args.prompt_mode:
        point_np = point_from_mask(prompt_source)
        if getattr(args, "augment", False):
            point_np = jitter_point(point_np, getattr(args, "point_jitter", 0.0), prompt_source.shape, rng)
        points = torch.from_numpy(point_np)[None, None].to(device)
        point_labels = torch.ones(1, 1, dtype=torch.long, device=device)
    if "mask" in args.prompt_mode:
        mask_np = sparse if mask_input_source == "sparse" else pseudo
        if getattr(args, "augment", False) and getattr(args, "mask_morph_jitter", 0) > 0:
            r = int(rng.integers(-int(args.mask_morph_jitter), int(args.mask_morph_jitter) + 1))
            mask_np = morph_binary_mask(mask_np, r)
        mask_inputs = torch.from_numpy(mask_np.astype(np.float32))[None, None].to(device)

    return {
        "case_id": row["case_id"],
        "image": image,
        "target": target,
        "sparse_target": sparse_target,
        "gt_target": gt_target,
        "prior": prior,
        "sup": sup,
        "valid": valid,
        "oar": oar,
        "lung": lung,
        "boxes": boxes,
        "points": points,
        "point_labels": point_labels,
        "mask_inputs": mask_inputs,
        "crop_info": crop_info,
        "annotated_z_patch": annotated_z,
    }


def main():
    parser = argparse.ArgumentParser(description="Sparse-supervised SAM-Med3D fine-tuning.")
    parser.add_argument("--metadata_csv", required=True)
    parser.add_argument("--save_dir", required=True)
    parser.add_argument("--log_dir", required=True)
    parser.add_argument("--prompt_mode", choices=["point", "box", "point_box", "mask", "point_box_mask"], default="point_box_mask")
    parser.add_argument("--prompt_source", choices=["sparse", "pseudo"], default="pseudo",
                        help="Backward-compatible source for point/box prompts.")
    parser.add_argument("--point_box_source", choices=["sparse", "pseudo"], default=None)
    parser.add_argument("--mask_input_source", choices=["sparse", "pseudo"], default="pseudo")
    parser.add_argument("--box_margin", type=int, default=6)
    parser.add_argument("--patch_size", type=int, nargs=3, default=[128, 128, 128])
    parser.add_argument("--crop_source", choices=["sparse", "pseudo"], default="pseudo")
    parser.add_argument("--supervision_mode", choices=["sparse", "full_gt", "pseudo"], default="sparse",
                        help="sparse: only annotated CTV slices; full_gt: oracle full label-5 supervision; pseudo: imitate pseudo label.")
    parser.add_argument("--augment", action="store_true",
                        help="Enable synchronized weak augmentation for single-case fine-tuning.")
    parser.add_argument("--crop_jitter", type=int, default=0,
                        help="Voxel jitter applied to the shared crop center. All arrays are cropped identically.")
    parser.add_argument("--point_jitter", type=float, default=0.0,
                        help="Std in voxels for point prompt jitter. Does not alter sparse supervision.")
    parser.add_argument("--box_margin_jitter", type=int, default=0,
                        help="Uniform integer jitter added to the box prompt margin.")
    parser.add_argument("--mask_morph_jitter", type=int, default=0,
                        help="Random erosion/dilation radius for mask prompt only.")
    parser.add_argument("--intensity_shift_range", type=float, default=0.0,
                        help="HU shift range applied only to CT image when --augment is enabled.")
    parser.add_argument("--intensity_scale_range", type=float, default=0.0,
                        help="Multiplicative CT scale jitter around 1.0 when --augment is enabled.")
    parser.add_argument("--gaussian_noise_std", type=float, default=0.0,
                        help="HU Gaussian noise std applied only to CT image when --augment is enabled.")
    parser.add_argument("--sam_root", default="/share3/home/huangyanxin/SAM-Med3D-main")
    parser.add_argument("--sam_checkpoint", default="/share3/home/huangyanxin/SAM-Med3D-main/ckpt/sam_med3d_turbo.pth")
    parser.add_argument("--sam_model_type", default="vit_b_ori")
    parser.add_argument("--freeze_image_encoder", action="store_true", default=True)
    parser.add_argument("--train_prompt_encoder", action="store_true")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--lambda_bce", type=float, default=1.0)
    parser.add_argument("--lambda_dice", type=float, default=1.0)
    parser.add_argument("--lambda_prior", type=float, default=0.05)
    parser.add_argument("--lambda_anat", type=float, default=0.05,
                        help="Penalty for predicted CTV probability inside labels 2/3/4.")
    parser.add_argument("--lambda_smooth", type=float, default=0.01)
    parser.add_argument("--pos_weight", type=float, default=4.0)
    parser.add_argument("--max_cases", type=int, default=0)
    parser.add_argument("--case_id", action="append", default=None)
    parser.add_argument("--target_label", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)
    ensure_dir(args.save_dir)
    ensure_dir(args.log_dir)
    with open(os.path.join(args.log_dir, "config.json"), "w") as f:
        json.dump(vars(args), f, indent=2)

    rows = load_rows(args.metadata_csv, max_cases=args.max_cases, case_id=args.case_id)
    if not rows:
        raise ValueError(f"No rows found in {args.metadata_csv}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model(
        "sam_med3d",
        sam_root=args.sam_root,
        checkpoint=args.sam_checkpoint,
        model_type=args.sam_model_type,
        freeze_image_encoder=args.freeze_image_encoder,
        freeze_prompt_encoder=not args.train_prompt_encoder,
        train_mask_decoder=True,
    ).to(device)
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=args.weight_decay)

    log_path = os.path.join(args.log_dir, "train_log.csv")
    with open(log_path, "w") as f:
        f.write("epoch,case_id,loss,bce,dice,prior,anat,smooth\n")

    best_loss = float("inf")
    for epoch in range(1, args.epochs + 1):
        np.random.shuffle(rows)
        model.train()
        epoch_losses = []
        for row in tqdm(rows, desc=f"SAM sparse epoch {epoch}/{args.epochs}"):
            sample = build_sample(row, args, device, rng=rng)
            out = model(
                sample["image"],
                boxes=sample["boxes"],
                points=sample["points"],
                point_labels=sample["point_labels"],
                mask_inputs=sample["mask_inputs"],
            )
            logits = out["logits"]
            prob = torch.sigmoid(logits)
            bce = bce_on_mask(logits, sample["target"], sample["sup"], pos_weight=args.pos_weight)
            dice = dice_loss_on_mask(prob, sample["target"], sample["sup"])
            prior = F.l1_loss(prob, sample["prior"])
            anat = (prob * sample["oar"]).mean()
            smooth = torch.abs(prob[:, :, 1:] - prob[:, :, :-1]).mean()
            loss = (
                args.lambda_bce * bce
                + args.lambda_dice * dice
                + args.lambda_prior * prior
                + args.lambda_anat * anat
                + args.lambda_smooth * smooth
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            epoch_losses.append(float(loss.detach().cpu()))
            with open(log_path, "a") as f:
                f.write(
                    f"{epoch},{sample['case_id']},{float(loss.detach().cpu()):.6f},"
                    f"{float(bce.detach().cpu()):.6f},{float(dice.detach().cpu()):.6f},"
                    f"{float(prior.detach().cpu()):.6f},{float(anat.detach().cpu()):.6f},"
                    f"{float(smooth.detach().cpu()):.6f}\n"
                )
        avg_loss = float(np.mean(epoch_losses))
        ckpt = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "args": vars(args),
            "avg_loss": avg_loss,
        }
        torch.save(ckpt, os.path.join(args.save_dir, "last.pth"))
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(ckpt, os.path.join(args.save_dir, "best.pth"))
        print(f"Epoch {epoch}: avg_loss={avg_loss:.6f} best={best_loss:.6f}")


if __name__ == "__main__":
    main()
