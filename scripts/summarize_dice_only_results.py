#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ROWS = [
    (
        "CTV",
        "nnU-Net 3d_fullres folds 0/1/2",
        "No prompt",
        "CTV",
        ROOT / "external_runs/metrics/nnunet_3d_fullres_folds012_final/ctv/summary.json",
        "1",
    ),
    ("CTV", "DiffUNet", "No prompt", "CTV", ROOT / "external_runs/metrics/diffunet/ctv/summary.json", "1"),
    (
        "CTV",
        "SAM-Med3D CT-derived",
        "Automatic CT prompt",
        "CTV",
        ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/ctv/summary.json",
        "1",
    ),
    (
        "CTV",
        "SAM-Med3D sparse-prompt K=7",
        "7 sparse CTV slices",
        "CTV",
        ROOT / "external_runs/metrics/sammed3d_sparse_prompt_k7_even_nonempty_click7/ctv/summary.json",
        "1",
    ),
    (
        "CTV",
        "SAM-Med3D full-GT prompt",
        "Oracle full-GT prompt",
        "CTV",
        ROOT / "external_runs/metrics/sammed3d_click10/ctv/summary.json",
        "1",
    ),
    (
        "OAR",
        "nnU-Net 3d_fullres folds 2/3/4",
        "No prompt",
        "Lung",
        ROOT / "external_runs/metrics/nnunet_3d_fullres_folds234_final/oar/summary.json",
        "1",
    ),
    (
        "OAR",
        "nnU-Net 3d_fullres folds 2/3/4",
        "No prompt",
        "Heart",
        ROOT / "external_runs/metrics/nnunet_3d_fullres_folds234_final/oar/summary.json",
        "2",
    ),
    (
        "OAR",
        "nnU-Net 3d_fullres folds 2/3/4",
        "No prompt",
        "Spinal cord",
        ROOT / "external_runs/metrics/nnunet_3d_fullres_folds234_final/oar/summary.json",
        "3",
    ),
    (
        "OAR",
        "nnU-Net 3d_fullres folds 2/3/4",
        "No prompt",
        "Esophagus",
        ROOT / "external_runs/metrics/nnunet_3d_fullres_folds234_final/oar/summary.json",
        "4",
    ),
    (
        "OAR",
        "SAM-Med3D CT-derived",
        "Automatic CT prompt",
        "Lung",
        ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/oar/summary.json",
        "1",
    ),
    (
        "OAR",
        "SAM-Med3D CT-derived",
        "Automatic CT prompt",
        "Heart",
        ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/oar/summary.json",
        "2",
    ),
    (
        "OAR",
        "SAM-Med3D CT-derived",
        "Automatic CT prompt",
        "Spinal cord",
        ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/oar/summary.json",
        "3",
    ),
    (
        "OAR",
        "SAM-Med3D CT-derived",
        "Automatic CT prompt",
        "Esophagus",
        ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/oar/summary.json",
        "4",
    ),
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


def read_dice(path, cls):
    if not path.exists():
        return None
    with path.open() as f:
        summary = json.load(f)
    metric = summary.get("per_class", {}).get(str(cls), {}).get("dice", {})
    if metric.get("mean") is None:
        return None
    return {
        "mean": float(metric["mean"]),
        "std": float(metric.get("std") or 0.0),
        "n": int(metric.get("n") or 0),
        "source": str(path),
    }


def collect_rows():
    out = []
    for task, method, prompt, cls_name, path, cls in ROWS:
        metric = read_dice(path, cls)
        if metric is None:
            continue
        out.append(
            {
                "task": task,
                "method": method,
                "prompt": prompt,
                "class": cls_name,
                "n": metric["n"],
                "dice_mean": metric["mean"],
                "dice_std": metric["std"],
                "dice": f"{metric['mean']:.3f} $\\pm$ {metric['std']:.3f}",
                "source": metric["source"],
            }
        )
    return out


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["task", "method", "prompt", "class", "n", "dice", "dice_mean", "dice_std", "source"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_tex(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\documentclass{article}",
        r"\usepackage{booktabs}",
        r"\usepackage[margin=1in]{geometry}",
        r"\begin{document}",
        r"\section*{Dice-only baseline results}",
        "Only Dice is reported in this table. Surface metrics are intentionally omitted.",
        "",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Dice-only baseline and SAM-Med3D prompt results on the independent test set.}",
        r"\label{tab:dice-only-results}",
        r"\begin{tabular}{llllrr}",
        r"\toprule",
        r"Task & Method & Prompt setting & Class & $n$ & Dice \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{tex_escape(row['task'])} & {tex_escape(row['method'])} & "
            f"{tex_escape(row['prompt'])} & {tex_escape(row['class'])} & "
            f"{row['n']} & {row['dice']} \\\\"
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
    parser.add_argument("--out_csv", default=None)
    parser.add_argument("--out_tex", default=None)
    args = parser.parse_args()

    rows = collect_rows()
    out_csv = Path(args.out_csv) if args.out_csv else ROOT / "reports" / "dice_only_baseline_results.csv"
    out_tex = Path(args.out_tex) if args.out_tex else ROOT / "reports" / "dice_only_baseline_results.tex"
    write_csv(out_csv, rows)
    write_tex(out_tex, rows)
    print("Wrote", out_csv)
    print("Wrote", out_tex)
    print("Rows:", len(rows))


if __name__ == "__main__":
    main()
