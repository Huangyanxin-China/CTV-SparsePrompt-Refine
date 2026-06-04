#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


METHODS = [
    {
        "group": "No prompt",
        "method": "nnU-Net 3d_fullres",
        "path": ROOT / "external_runs/metrics/nnunet_3d_fullres_folds012_final/ctv/summary.json",
        "schema": "seg_folder",
    },
    {
        "group": "No prompt",
        "method": "DiffUNet",
        "path": ROOT / "external_runs/metrics/diffunet/ctv/summary.json",
        "schema": "seg_folder",
    },
    {
        "group": "Automatic prompt",
        "method": "SAM-Med3D CT-derived",
        "path": ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/ctv/summary.json",
        "schema": "seg_folder",
    },
    {
        "group": "Sparse prompt",
        "method": "SAM-Med3D sparse K=7",
        "path": ROOT / "external_runs/metrics/sammed3d_sparse_prompt_k7_even_nonempty_click7/ctv/summary.json",
        "schema": "seg_folder",
    },
    {
        "group": "Sparse prompt",
        "method": "Our SDF pseudo K=7",
        "path": ROOT / "results/our_sdf_pseudo_k7_even_from_sam_prompts/summary.json",
        "schema": "our_sdf",
    },
    {
        "group": "Oracle",
        "method": "SAM-Med3D full-GT prompt",
        "path": ROOT / "external_runs/metrics/sammed3d_click10/ctv/summary.json",
        "schema": "seg_folder",
    },
]


def tex_escape(text):
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(ch, ch) for ch in str(text))


def fmt(metric, digits=3):
    if not metric or metric.get("mean") is None:
        return "--"
    return f"{metric['mean']:.{digits}f} $\\pm$ {metric.get('std', 0.0):.{digits}f}"


def metric_value(metric, key):
    if not metric or metric.get("mean") is None:
        return ""
    return metric.get(key, "")


def read_method(row):
    if not row["path"].exists():
        return None
    with row["path"].open() as f:
        summary = json.load(f)

    if row["schema"] == "seg_folder":
        metrics = summary.get("per_class", {}).get("1", {})
    else:
        metrics = summary.get("metrics", {})

    return {
        "group": row["group"],
        "method": row["method"],
        "n": metrics.get("dice", {}).get("n", summary.get("num_predictions", "")),
        "dice": fmt(metrics.get("dice", {}), 3),
        "dice_mean": metric_value(metrics.get("dice", {}), "mean"),
        "dice_std": metric_value(metrics.get("dice", {}), "std"),
        "unseen_dice": fmt(metrics.get("dice_unseen_slices", {}), 3),
        "unseen_dice_mean": metric_value(metrics.get("dice_unseen_slices", {}), "mean"),
        "unseen_dice_std": metric_value(metrics.get("dice_unseen_slices", {}), "std"),
        "hd95": fmt(metrics.get("hd95", {}), 2),
        "hd95_mean": metric_value(metrics.get("hd95", {}), "mean"),
        "hd95_std": metric_value(metrics.get("hd95", {}), "std"),
        "asd": fmt(metrics.get("asd", {}), 2),
        "asd_mean": metric_value(metrics.get("asd", {}), "mean"),
        "asd_std": metric_value(metrics.get("asd", {}), "std"),
        "volume_diff_percent": fmt(metrics.get("volume_diff_percent", {}), 1),
        "volume_diff_percent_mean": metric_value(metrics.get("volume_diff_percent", {}), "mean"),
        "volume_diff_percent_std": metric_value(metrics.get("volume_diff_percent", {}), "std"),
        "source": str(row["path"]),
    }


def collect_rows():
    return [r for r in (read_method(m) for m in METHODS) if r is not None]


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "group",
        "method",
        "n",
        "dice",
        "dice_mean",
        "dice_std",
        "unseen_dice",
        "unseen_dice_mean",
        "unseen_dice_std",
        "hd95",
        "hd95_mean",
        "hd95_std",
        "asd",
        "asd_mean",
        "asd_std",
        "volume_diff_percent",
        "volume_diff_percent_mean",
        "volume_diff_percent_std",
        "source",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_tex(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\documentclass{article}",
        r"\usepackage{booktabs}",
        r"\usepackage[margin=1in]{geometry}",
        r"\begin{document}",
        r"\section*{CTV main experiment results}",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{CTV segmentation and sparse-prompt completion results on the independent test set.}",
        r"\label{tab:ctv-main-results}",
        r"\begin{tabular}{lllrrrrr}",
        r"\toprule",
        r"Group & Method & $n$ & Dice & Unseen Dice & HD95 (mm) & ASD (mm) & Vol. diff. (\%) \\",
        r"\midrule",
    ]
    for r in rows:
        lines.append(
            f"{tex_escape(r['group'])} & {tex_escape(r['method'])} & {r['n']} & "
            f"{r['dice']} & {r['unseen_dice']} & {r['hd95']} & {r['asd']} & {r['volume_diff_percent']} \\\\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        r"\end{document}",
        "",
    ]
    path.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_csv", default=str(ROOT / "reports" / "ctv_main_experiment_results.csv"))
    parser.add_argument("--out_tex", default=str(ROOT / "reports" / "ctv_main_experiment_results.tex"))
    args = parser.parse_args()

    rows = collect_rows()
    write_csv(Path(args.out_csv), rows)
    write_tex(Path(args.out_tex), rows)
    print("Wrote", args.out_csv)
    print("Wrote", args.out_tex)
    print("Rows:", len(rows))


if __name__ == "__main__":
    main()
