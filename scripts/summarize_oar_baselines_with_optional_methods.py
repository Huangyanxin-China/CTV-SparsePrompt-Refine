#!/usr/bin/env python3
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "reports" / "oar_baseline_results_with_optional_methods.csv"
OUT_TEX = ROOT / "reports" / "oar_baseline_results_with_optional_methods.tex"
OUT_MD = ROOT / "reports" / "oar_baseline_results_with_optional_methods.md"


METHODS = [
    ("Fully automatic", "nnU-Net", ROOT / "external_runs/metrics/nnunet_3d_fullres_folds234_final/oar/summary.json"),
    ("Fully automatic", "DiffUNet", ROOT / "external_runs/metrics/diffunet/oar/summary.json"),
    (
        "Fully automatic",
        "U-Mamba",
        [
            ROOT / "external_runs/metrics/umamba/oar/summary.json",
            ROOT / "external_runs_umamba_bs1/metrics/umamba/oar/summary.json",
        ],
    ),
    (
        "Automatic prompt",
        "SAM-Med3D CT-derived prompt",
        ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/oar/summary.json",
    ),
    ("Oracle prompt", "SAM-Med3D full-GT prompt", ROOT / "external_runs/metrics/sammed3d_click10/oar/summary.json"),
]

CLASSES = [("1", "Lung"), ("2", "Heart"), ("3", "Spinal cord"), ("4", "Esophagus")]


def load(path):
    with path.open() as f:
        return json.load(f)


def fmt(metric, digits=3):
    if not metric or metric.get("mean") is None:
        return "--"
    return f"{metric['mean']:.{digits}f} ± {metric.get('std', 0.0):.{digits}f}"


def fmt_tex(metric, digits=3):
    if not metric or metric.get("mean") is None:
        return "--"
    return f"{metric['mean']:.{digits}f} $\\pm$ {metric.get('std', 0.0):.{digits}f}"


def tex_escape(text):
    repl = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#"}
    return "".join(repl.get(ch, ch) for ch in str(text))

def metric_tex(text):
    return str(text).replace("±", r"$\pm$")



def first_existing(paths):
    if isinstance(paths, (list, tuple)):
        for path in paths:
            if path.exists():
                return path, []
        return None, [str(path.relative_to(ROOT)) for path in paths]
    if paths.exists():
        return paths, []
    return None, [str(paths.relative_to(ROOT))]


def collect_rows():
    rows = []
    missing = []
    for group, method, paths in METHODS:
        path, missing_paths = first_existing(paths)
        if path is None:
            missing.extend(missing_paths)
            continue
        summary = load(path)
        per_class = summary.get("per_class", {})
        for class_id, class_name in CLASSES:
            metrics = per_class.get(class_id, {})
            rows.append(
                {
                    "group": group,
                    "method": method,
                    "organ": class_name,
                    "dice": fmt(metrics.get("dice", {}), 3),
                    "hd95": fmt(metrics.get("hd95", {}), 2),
                    "asd": fmt(metrics.get("asd", {}), 2),
                    "volume_diff_percent": fmt(metrics.get("volume_diff_percent", {}), 1),
                    "source": str(path.relative_to(ROOT)),
                }
            )
    return rows, missing


def write_csv(rows):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["group", "method", "organ", "dice", "hd95", "asd", "volume_diff_percent", "source"]
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_md(rows, missing):
    lines = [
        "# OAR Baseline Results",
        "",
        "| Group | Method | Organ | Dice | HD95 (mm) | ASD (mm) | Vol. diff. (%) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['group']} | {row['method']} | {row['organ']} | {row['dice']} | {row['hd95']} | {row['asd']} | {row['volume_diff_percent']} |"
        )
    if missing:
        lines += ["", "Missing metric files:", ""]
        lines += [f"- `{item}`" for item in missing]
    OUT_MD.write_text("\n".join(lines) + "\n")


def write_tex(rows):
    lines = [
        r"\documentclass{article}",
        r"\usepackage{booktabs}",
        r"\usepackage[margin=1in]{geometry}",
        r"\begin{document}",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Thoracic OAR segmentation baseline results.}",
        r"\label{tab:oar-baselines}",
        r"\begin{tabular}{lllrrrr}",
        r"\toprule",
        r"Group & Method & Organ & Dice & HD95 (mm) & ASD (mm) & Vol. diff. (\%) \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{tex_escape(row['group'])} & {tex_escape(row['method'])} & {tex_escape(row['organ'])} & "
            f"{metric_tex(row['dice'])} & {metric_tex(row['hd95'])} & "
            f"{metric_tex(row['asd'])} & {metric_tex(row['volume_diff_percent'])} \\\\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        r"\end{document}",
        "",
    ]
    OUT_TEX.write_text("\n".join(lines))

def main():
    rows, missing = collect_rows()
    write_csv(rows)
    write_md(rows, missing)
    write_tex(rows)
    print("Wrote", OUT_CSV)
    print("Wrote", OUT_MD)
    print("Wrote", OUT_TEX)
    if missing:
        print("Missing:")
        for item in missing:
            print(" ", item)


if __name__ == "__main__":
    main()
