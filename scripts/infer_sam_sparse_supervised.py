import argparse
import csv
import os
import sys

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def load_config_from_checkpoint(checkpoint):
    if not checkpoint:
        return {}, None
    import torch

    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    return ckpt.get("args", {}), ckpt.get("model_state_dict", ckpt)


def main():
    parser = argparse.ArgumentParser(description="Infer/evaluate sparse-supervised SAM-Med3D.")
    parser.add_argument("--metadata_csv", required=True)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--metrics_csv", required=True)
    parser.add_argument("--prompt_mode", choices=["point", "box", "point_box", "mask", "point_box_mask"], default="")
    parser.add_argument("--prompt_source", choices=["sparse", "pseudo"], default="")
    parser.add_argument("--point_box_source", choices=["sparse", "pseudo"], default="")
    parser.add_argument("--mask_input_source", choices=["sparse", "pseudo"], default="")
    parser.add_argument("--box_margin", type=int, default=-1)
    parser.add_argument("--patch_size", type=int, nargs=3, default=None)
    parser.add_argument("--crop_source", choices=["sparse", "pseudo"], default="")
    parser.add_argument("--sam_root", default="/share3/home/huangyanxin/SAM-Med3D-main")
    parser.add_argument("--sam_checkpoint", default="/share3/home/huangyanxin/SAM-Med3D-main/ckpt/sam_med3d_turbo.pth")
    parser.add_argument("--sam_model_type", default="vit_b_ori")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--max_cases", type=int, default=0)
    parser.add_argument("--case_id", action="append", default=None)
    parser.add_argument("--target_label", type=int, default=5)
    args = parser.parse_args()

    import torch
    from tqdm import tqdm

    from models import create_model
    from scripts.train_sam_sparse_supervised import build_sample, load_rows, paste_patch_3d, target_binary_mask
    from utils.io import ensure_dir, read_image, write_like
    from utils.metrics import dice_score, hd95_asd

    ckpt_args, state_dict = load_config_from_checkpoint(args.checkpoint)
    prompt_mode = args.prompt_mode or ckpt_args.get("prompt_mode", "point_box_mask")
    prompt_source = args.prompt_source or ckpt_args.get("prompt_source", "pseudo")
    point_box_source = args.point_box_source or ckpt_args.get("point_box_source", prompt_source)
    mask_input_source = args.mask_input_source or ckpt_args.get("mask_input_source", "pseudo")
    box_margin = args.box_margin if args.box_margin >= 0 else int(ckpt_args.get("box_margin", 6))
    patch_size = args.patch_size or ckpt_args.get("patch_size", [128, 128, 128])
    crop_source = args.crop_source or ckpt_args.get("crop_source", "pseudo")

    rows = load_rows(args.metadata_csv, max_cases=args.max_cases, case_id=args.case_id)
    if not rows:
        raise ValueError(f"No rows matched metadata={args.metadata_csv} case_id={args.case_id}")
    ensure_dir(args.output_dir)
    ensure_dir(os.path.dirname(args.metrics_csv))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model(
        "sam_med3d",
        sam_root=args.sam_root,
        checkpoint=args.sam_checkpoint,
        model_type=args.sam_model_type,
        freeze_image_encoder=True,
        freeze_prompt_encoder=True,
        train_mask_decoder=False,
    ).to(device)
    if args.checkpoint and state_dict is not None:
        missing, unexpected = model.load_state_dict(state_dict, strict=False)
        print(f"Loaded checkpoint: {args.checkpoint}")
        if missing:
            print(f"Missing keys: {len(missing)}")
        if unexpected:
            print(f"Unexpected keys: {len(unexpected)}")
    model.eval()

    metric_rows = []
    shim_args = argparse.Namespace(
        prompt_mode=prompt_mode,
        prompt_source=prompt_source,
        point_box_source=point_box_source,
        mask_input_source=mask_input_source,
        box_margin=box_margin,
        patch_size=patch_size,
        crop_source=crop_source,
        target_label=args.target_label,
    )
    for row in tqdm(rows, desc="SAM sparse inference"):
        sample = build_sample(row, shim_args, device)
        with torch.no_grad():
            out = model(
                sample["image"],
                boxes=sample["boxes"],
                points=sample["points"],
                point_labels=sample["point_labels"],
                mask_inputs=sample["mask_inputs"],
            )
            prob_patch = torch.sigmoid(out["logits"])[0, 0].detach().cpu().numpy()
        pred_patch = (prob_patch >= float(args.threshold)).astype(np.uint8)
        gt_np, gt_itk = read_image(row["source_label_path"])
        gt = gt_np == int(args.target_label)
        pseudo_np, _ = read_image(row["pseudo_label_path"])
        pseudo = target_binary_mask(pseudo_np, target_label=args.target_label).astype(bool)
        prob = paste_patch_3d(prob_patch.astype(np.float32), sample["crop_info"], fill_value=0.0)
        pred = paste_patch_3d(pred_patch, sample["crop_info"], fill_value=0).astype(np.uint8)
        annotated_z = [int(v) for v in str(row.get("annotated_z", "")).split(";") if v != ""]
        ann_mask = np.zeros(gt.shape, dtype=bool)
        for z in annotated_z:
            if 0 <= z < gt.shape[0]:
                ann_mask[z] = True
        unann_mask = ~ann_mask
        image_np, image_itk = read_image(row["image_path"])
        pred_path = os.path.join(args.output_dir, f"{row['case_id']}_sam_pred.nii.gz")
        prob_path = os.path.join(args.output_dir, f"{row['case_id']}_sam_prob.nii.gz")
        write_like(pred, image_itk, pred_path, dtype=np.uint8)
        write_like(prob.astype(np.float32), image_itk, prob_path, dtype=np.float32)
        hd95, asd = hd95_asd(pred, gt, spacing_xyz=gt_itk.GetSpacing())
        metric_rows.append(
            {
                "case_id": row["case_id"],
                "prompt_mode": prompt_mode,
                "prompt_source": prompt_source,
                "threshold": float(args.threshold),
                "dice": dice_score(pred, gt),
                "dice_to_pseudo": dice_score(pred, pseudo),
                "dice_annotated": dice_score(pred[ann_mask], gt[ann_mask]) if ann_mask.any() else np.nan,
                "dice_unannotated": dice_score(pred[unann_mask], gt[unann_mask]) if unann_mask.any() else np.nan,
                "hd95": hd95,
                "asd": asd,
                "pred_foreground": int(pred.sum()),
                "gt_foreground": int(gt.sum()),
                "pred_path": pred_path,
                "prob_path": prob_path,
                "pseudo_label_path": row["pseudo_label_path"],
            }
        )

    with open(args.metrics_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(metric_rows[0].keys()))
        writer.writeheader()
        writer.writerows(metric_rows)
    print(f"Saved metrics: {args.metrics_csv}")
    if metric_rows:
        mean_dice = float(np.mean([r["dice"] for r in metric_rows]))
        print(f"Mean Dice: {mean_dice:.6f}")


if __name__ == "__main__":
    main()
