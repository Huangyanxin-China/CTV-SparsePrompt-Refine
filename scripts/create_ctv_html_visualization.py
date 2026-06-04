#!/usr/bin/env python3
import argparse
import csv
import html
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import SimpleITK as sitk


ROOT = Path(__file__).resolve().parents[1]

CT_DIR = ROOT / "nnunet_runs/raw/Dataset015_CTV_Dataset004Split/imagesTs"
GT_DIR = ROOT / "nnunet_runs/raw/Dataset015_CTV_Dataset004Split/labelsTs"
PROMPT_DIR = ROOT / "external_runs/sammed3d_sparse_prompt/ctv_k7_even_nonempty_click7/_sparse_prompts"

METHODS = [
    {
        "key": "nnunet",
        "name": "nnU-Net",
        "path": ROOT / "external_runs/nnunet/nnunet_3d_fullres_folds012_final/ctv",
        "color": "#ff7f0e",
    },
    {
        "key": "diffunet",
        "name": "DiffUNet",
        "path": ROOT / "external_runs/diffunet/ctv/predictions",
        "color": "#17becf",
    },
    {
        "key": "sam_ct",
        "name": "SAM CT prompt",
        "path": ROOT / "external_runs/sammed3d_nonoracle/ctv_ct_heuristic_click1",
        "color": "#8c564b",
    },
    {
        "key": "sam_k7",
        "name": "SAM K=7",
        "path": ROOT / "external_runs/sammed3d_sparse_prompt/ctv_k7_even_nonempty_click7",
        "color": "#9467bd",
    },
    {
        "key": "sam_oracle",
        "name": "SAM oracle",
        "path": ROOT / "external_runs/sammed3d/predictions/ctv_click10",
        "color": "#e377c2",
    },
    {
        "key": "our_sdf",
        "name": "Our SDF",
        "path": ROOT / "results/our_sdf_pseudo_k7_even_from_sam_prompts/labels",
        "color": "#d62728",
    },
    {
        "key": "core_only",
        "name": "Core-only",
        "path": ROOT / "results/core_envelope_oar_refine_k7_current/predictions/core_only",
        "color": "#bcbd22",
    },
    {
        "key": "hu_oar",
        "name": "HU/OAR refine",
        "path": ROOT / "results/core_envelope_oar_refine_k7_current/predictions/hu_support_refine_oar",
        "color": "#1f77b4",
    },
]


def read_array(path):
    return sitk.GetArrayFromImage(sitk.ReadImage(str(path)))


def read_bool(path):
    if not path.exists():
        return None
    return read_array(path) > 0


def normalize_ct(slice2d):
    image = np.clip(slice2d.astype(np.float32), -1000, 600)
    return (image + 1000.0) / 1600.0


def dice(pred, gt):
    if pred is None:
        return None
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    denom = int(pred.sum()) + int(gt.sum())
    if denom == 0:
        return 1.0
    return float(2.0 * np.logical_and(pred, gt).sum() / denom)


def slice_dice(pred, gt, z):
    if pred is None:
        return None
    return dice(pred[z], gt[z])


def choose_slices(gt, prompt):
    gt_area = gt.reshape(gt.shape[0], -1).sum(axis=1)
    prompt_area = prompt.reshape(prompt.shape[0], -1).sum(axis=1) if prompt is not None else np.zeros(gt.shape[0])
    prompt_z = np.where(prompt_area > 0)[0]
    if prompt_z.size:
        prompt_slice = int(prompt_z[np.argmax(gt_area[prompt_z])])
    else:
        prompt_slice = int(np.argmax(gt_area))

    unseen_mask = gt_area > 0
    if prompt_z.size:
        unseen_mask[prompt_z] = False
    unseen_z = np.where(unseen_mask)[0]
    if unseen_z.size:
        unseen_slice = int(unseen_z[np.argmax(gt_area[unseen_z])])
    else:
        unseen_slice = int(np.argmax(gt_area))
    return prompt_slice, unseen_slice


def bbox_crop(mask2d, pad=45):
    pts = np.argwhere(mask2d)
    if pts.size == 0:
        return slice(None), slice(None)
    y0, x0 = pts.min(axis=0)
    y1, x1 = pts.max(axis=0) + 1
    h, w = mask2d.shape
    return slice(max(0, y0 - pad), min(h, y1 + pad)), slice(max(0, x0 - pad), min(w, x1 + pad))


def crop_for_slice(gt, prompt, masks, z):
    crop_mask = gt[z].copy()
    if prompt is not None:
        crop_mask |= prompt[z]
    for key in ("our_sdf", "core_only", "sam_k7", "nnunet"):
        mask = masks.get(key)
        if mask is not None:
            crop_mask |= mask[z]
    return bbox_crop(crop_mask, pad=45)


def draw_contour(ax, mask2d, color, label, linewidth=1.4):
    if mask2d is None or mask2d.sum() == 0:
        return
    ax.contour(mask2d.astype(float), levels=[0.5], colors=[color], linewidths=linewidth)
    ax.plot([], [], color=color, linewidth=linewidth, label=label)


def render_case(case_id, out_png):
    ct = read_array(CT_DIR / f"{case_id}_0000.nii.gz")
    gt = read_bool(GT_DIR / f"{case_id}.nii.gz")
    prompt = read_bool(PROMPT_DIR / f"{case_id}.nii.gz")
    masks = {spec["key"]: read_bool(spec["path"] / f"{case_id}.nii.gz") for spec in METHODS}

    prompt_slice, unseen_slice = choose_slices(gt, prompt)
    rows = [("Prompt slice", prompt_slice), ("Unseen slice", unseen_slice)]
    columns = [("GT", None)] + [("Sparse prompt", "prompt")] + [(spec["name"], spec["key"]) for spec in METHODS]

    fig, axes = plt.subplots(len(rows), len(columns), figsize=(2.65 * len(columns), 5.7), constrained_layout=True)
    if axes.ndim == 1:
        axes = axes[None, :]

    global_dice = {spec["key"]: dice(masks[spec["key"]], gt) for spec in METHODS}

    for row_idx, (row_name, z) in enumerate(rows):
        crop_y, crop_x = crop_for_slice(gt, prompt, masks, z)
        for col_idx, (title, key) in enumerate(columns):
            ax = axes[row_idx, col_idx]
            ax.imshow(normalize_ct(ct[z])[crop_y, crop_x], cmap="gray")
            draw_contour(ax, gt[z][crop_y, crop_x], "#2ca02c", "GT", linewidth=1.6)

            title_text = title
            if key == "prompt":
                draw_contour(ax, prompt[z][crop_y, crop_x] if prompt is not None else None, "#1f77b4", "Prompt", linewidth=1.6)
            elif key is not None:
                spec = next(item for item in METHODS if item["key"] == key)
                mask = masks.get(key)
                draw_contour(ax, mask[z][crop_y, crop_x] if mask is not None else None, spec["color"], title, linewidth=1.4)
                sd = slice_dice(mask, gt, z)
                gd = global_dice.get(key)
                if gd is not None and sd is not None:
                    title_text = f"{title}\nD={gd:.3f}, zD={sd:.3f}"
                elif gd is not None:
                    title_text = f"{title}\nD={gd:.3f}"

            if col_idx == 0:
                ax.set_ylabel(f"{row_name}\nz={z}", fontsize=9)
            ax.set_title(title_text, fontsize=8)
            ax.set_xticks([])
            ax.set_yticks([])

    handles, labels = axes[0, -1].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=min(5, len(handles)), fontsize=8)
    fig.suptitle(f"CTV segmentation comparison: {case_id}", fontsize=13)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)

    return {
        "case": case_id,
        "prompt_slice": prompt_slice,
        "unseen_slice": unseen_slice,
        **{f"{key}_dice": value for key, value in global_dice.items()},
    }


def fmt(value):
    if value is None or value == "":
        return "--"
    return f"{float(value):.3f}"


def write_index(out_dir, rows):
    assets_dir = out_dir / "assets"
    columns = [
        ("nnU-Net", "nnunet_dice"),
        ("DiffUNet", "diffunet_dice"),
        ("SAM CT", "sam_ct_dice"),
        ("SAM K=7", "sam_k7_dice"),
        ("SAM oracle", "sam_oracle_dice"),
        ("Our SDF", "our_sdf_dice"),
        ("Core-only", "core_only_dice"),
        ("HU/OAR", "hu_oar_dice"),
    ]
    table_rows = []
    for row in rows:
        image_rel = f"assets/{row['case']}.png"
        metric_cells = "".join(f"<td>{fmt(row.get(key))}</td>" for _, key in columns)
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(row['case'])}</td>"
            f"<td>{row['prompt_slice']}</td>"
            f"<td>{row['unseen_slice']}</td>"
            f"{metric_cells}"
            f"<td><a href=\"{image_rel}\">open</a></td>"
            "</tr>"
            f"<tr><td colspan=\"{len(columns) + 4}\"><img src=\"{image_rel}\" alt=\"{html.escape(row['case'])}\" loading=\"lazy\"></td></tr>"
        )
    metric_headers = "".join(f"<th>{html.escape(name)}</th>" for name, _ in columns)
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CTV Segmentation Test-Set Visualization</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f7f8; color: #1f2328; }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    p {{ margin: 6px 0 16px; }}
    table {{ border-collapse: collapse; width: 100%; background: #ffffff; }}
    th, td {{ border: 1px solid #d8dee4; padding: 6px 8px; font-size: 13px; text-align: left; }}
    th {{ background: #eef1f4; position: sticky; top: 0; z-index: 1; }}
    img {{ width: 100%; max-width: 2200px; display: block; margin: 8px auto 18px; border: 1px solid #d8dee4; background: #ffffff; }}
    a {{ color: #0969da; }}
    .small {{ color: #57606a; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>CTV Segmentation Test-Set Visualization</h1>
  <p class="small">Each case shows one sparse-prompt slice and one unseen slice. Green contour is GT; other contours are method outputs or sparse prompts.</p>
  <table>
    <thead>
      <tr>
        <th>Case</th>
        <th>Prompt z</th>
        <th>Unseen z</th>
        {metric_headers}
        <th>Image</th>
      </tr>
    </thead>
    <tbody>
      {''.join(table_rows)}
    </tbody>
  </table>
</body>
</html>
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(document)
    with (out_dir / "per_case_dice.csv").open("w", newline="") as f:
        fieldnames = ["case", "prompt_slice", "unseen_slice"] + [key for _, key in columns]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    print("Wrote", out_dir / "index.html")
    print("Wrote", out_dir / "per_case_dice.csv")
    print("Assets:", assets_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", default=str(ROOT / "reports" / "html_ctv_visualization"))
    parser.add_argument("--max_cases", type=int, default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    assets_dir = out_dir / "assets"
    case_ids = sorted(path.name[:-7] for path in GT_DIR.glob("*.nii.gz"))
    if args.max_cases is not None:
        case_ids = case_ids[: args.max_cases]

    rows = []
    for idx, case_id in enumerate(case_ids, 1):
        out_png = assets_dir / f"{case_id}.png"
        print(f"[{idx}/{len(case_ids)}] Rendering {case_id}")
        rows.append(render_case(case_id, out_png))
    write_index(out_dir, rows)


if __name__ == "__main__":
    main()
