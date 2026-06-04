#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


ROWS = [
    {
        "group": "No target prompt",
        "method": "nnU-Net 3d_fullres",
        "source": ROOT / "external_runs/metrics/nnunet_3d_fullres_folds012_final/ctv/summary.json",
        "schema": "seg_folder",
        "note": "3-fold ensemble, folds 0/1/2",
    },
    {
        "group": "No target prompt",
        "method": "DiffUNet",
        "source": ROOT / "external_runs/metrics/diffunet/ctv/summary.json",
        "schema": "seg_folder",
        "note": "automatic CTV baseline",
    },
    {
        "group": "Automatic SAM prompt",
        "method": "SAM-Med3D CT-derived prompt",
        "source": ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/ctv/summary.json",
        "schema": "seg_folder",
        "note": "CT-heuristic prompt, no GT at inference",
    },
    {
        "group": "Sparse target prompt",
        "method": "SAM-Med3D K=7 sparse prompt",
        "source": ROOT / "external_runs/metrics/sammed3d_sparse_prompt_k7_even_nonempty_click7/ctv/summary.json",
        "schema": "seg_folder",
        "note": "7 simulated sparse target slices",
    },
    {
        "group": "Sparse target prompt",
        "method": "Our SDF propagation K=7",
        "source": ROOT / "results/core_envelope_oar_refine_k7_current/full_summary.json",
        "schema": "core_method",
        "method_key": "sdf_base",
        "note": "SDF pseudo label from the same K=7 prompts",
    },
    {
        "group": "Sparse target prompt",
        "method": "Our core-only refinement",
        "source": ROOT / "results/core_envelope_oar_refine_k7_current/full_summary.json",
        "schema": "core_method",
        "method_key": "core_only",
        "note": "high-precision core from SDF candidate support",
    },
    {
        "group": "Sparse target prompt",
        "method": "Our HU/support/OAR refinement",
        "source": ROOT / "results/core_envelope_oar_refine_k7_current/full_summary.json",
        "schema": "core_method",
        "method_key": "hu_support_refine_oar",
        "note": "cluster-free HU/support filtering inside envelope",
    },
    {
        "group": "Diagnostic",
        "method": "Core-envelope envelope",
        "source": ROOT / "results/core_envelope_oar_refine_k7_current/full_summary.json",
        "schema": "core_method",
        "method_key": "envelope",
        "note": "high-recall envelope diagnostic",
    },
    {
        "group": "Oracle",
        "method": "SAM-Med3D full-GT prompt",
        "source": ROOT / "external_runs/metrics/sammed3d_click10/ctv/summary.json",
        "schema": "seg_folder",
        "note": "oracle full-mask-derived prompt baseline",
    },
    {
        "group": "Oracle",
        "method": "Core-envelope oracle upper bound",
        "source": ROOT / "results/core_envelope_oar_refine_k7_current/full_summary.json",
        "schema": "core_method",
        "method_key": "oracle_upper_bound",
        "note": "uses GT only to select best possible core/envelope inclusion",
    },
]


def load_json(path):
    with Path(path).open() as f:
        return json.load(f)


def seg_folder_metrics(summary):
    return summary.get("per_class", {}).get("1", summary.get("overall_foreground", {}))


def core_method_metrics(summary, method_key):
    return summary.get("methods", {}).get(method_key, {})


def metric(metrics, name):
    return metrics.get(name, {})


def mean(metrics, name):
    value = metric(metrics, name).get("mean")
    return "" if value is None else value


def std(metrics, name):
    value = metric(metrics, name).get("std")
    return "" if value is None else value


def n_value(metrics):
    for key in ("dice", "hd95", "asd"):
        n = metric(metrics, key).get("n")
        if n is not None:
            return n
    return ""


def fmt_mean_std(metrics, name, digits):
    m = mean(metrics, name)
    s = std(metrics, name)
    if m == "":
        return "--"
    if s == "":
        s = 0.0
    return f"{m:.{digits}f} ± {s:.{digits}f}"


def fmt_tex_mean_std(metrics, name, digits):
    m = mean(metrics, name)
    s = std(metrics, name)
    if m == "":
        return "--"
    if s == "":
        s = 0.0
    return f"{m:.{digits}f} $\\pm$ {s:.{digits}f}"


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


def read_row(row):
    if not row["source"].exists():
        return None
    summary = load_json(row["source"])
    if row["schema"] == "seg_folder":
        metrics = seg_folder_metrics(summary)
    elif row["schema"] == "core_method":
        metrics = core_method_metrics(summary, row["method_key"])
    else:
        raise ValueError(f"Unknown schema: {row['schema']}")

    out = {
        "group": row["group"],
        "method": row["method"],
        "n": n_value(metrics),
        "dice": fmt_mean_std(metrics, "dice", 3),
        "dice_mean": mean(metrics, "dice"),
        "dice_std": std(metrics, "dice"),
        "prompt_dice": fmt_mean_std(metrics, "dice_prompt_slices", 3),
        "prompt_dice_mean": mean(metrics, "dice_prompt_slices"),
        "prompt_dice_std": std(metrics, "dice_prompt_slices"),
        "unseen_dice": fmt_mean_std(metrics, "dice_unseen_slices", 3),
        "unseen_dice_mean": mean(metrics, "dice_unseen_slices"),
        "unseen_dice_std": std(metrics, "dice_unseen_slices"),
        "precision": fmt_mean_std(metrics, "precision", 3),
        "precision_mean": mean(metrics, "precision"),
        "precision_std": std(metrics, "precision"),
        "recall": fmt_mean_std(metrics, "recall", 3),
        "recall_mean": mean(metrics, "recall"),
        "recall_std": std(metrics, "recall"),
        "hd95": fmt_mean_std(metrics, "hd95", 2),
        "hd95_mean": mean(metrics, "hd95"),
        "hd95_std": std(metrics, "hd95"),
        "asd": fmt_mean_std(metrics, "asd", 2),
        "asd_mean": mean(metrics, "asd"),
        "asd_std": std(metrics, "asd"),
        "volume_diff_percent": fmt_mean_std(metrics, "volume_diff_percent", 1),
        "volume_diff_percent_mean": mean(metrics, "volume_diff_percent"),
        "volume_diff_percent_std": std(metrics, "volume_diff_percent"),
        "note": row["note"],
        "source": str(row["source"].relative_to(ROOT)),
    }
    return out


def collect_rows():
    return [row for row in (read_row(spec) for spec in ROWS) if row is not None]


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "group",
        "method",
        "n",
        "dice",
        "dice_mean",
        "dice_std",
        "prompt_dice",
        "prompt_dice_mean",
        "prompt_dice_std",
        "unseen_dice",
        "unseen_dice_mean",
        "unseen_dice_std",
        "precision",
        "precision_mean",
        "precision_std",
        "recall",
        "recall_mean",
        "recall_std",
        "hd95",
        "hd95_mean",
        "hd95_std",
        "asd",
        "asd_mean",
        "asd_std",
        "volume_diff_percent",
        "volume_diff_percent_mean",
        "volume_diff_percent_std",
        "note",
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
        r"\usepackage{graphicx}",
        r"\usepackage[margin=0.5in]{geometry}",
        r"\begin{document}",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{CTV baseline and sparse-prompt refinement results on the independent test set.}",
        r"\label{tab:ctv-all-results}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lllrrrrrrrr}",
        r"\toprule",
        r"Group & Method & $n$ & Dice & Prompt Dice & Unseen Dice & Precision & Recall & HD95 (mm) & ASD (mm) & Vol. diff. (\%) \\",
        r"\midrule",
    ]
    for row in rows:
        source = next(spec for spec in ROWS if spec["method"] == row["method"])
        summary = load_json(source["source"])
        if source["schema"] == "seg_folder":
            metrics = seg_folder_metrics(summary)
        else:
            metrics = core_method_metrics(summary, source["method_key"])
        lines.append(
            f"{tex_escape(row['group'])} & {tex_escape(row['method'])} & {row['n']} & "
            f"{fmt_tex_mean_std(metrics, 'dice', 3)} & "
            f"{fmt_tex_mean_std(metrics, 'dice_prompt_slices', 3)} & "
            f"{fmt_tex_mean_std(metrics, 'dice_unseen_slices', 3)} & "
            f"{fmt_tex_mean_std(metrics, 'precision', 3)} & "
            f"{fmt_tex_mean_std(metrics, 'recall', 3)} & "
            f"{fmt_tex_mean_std(metrics, 'hd95', 2)} & "
            f"{fmt_tex_mean_std(metrics, 'asd', 2)} & "
            f"{fmt_tex_mean_std(metrics, 'volume_diff_percent', 1)} \\\\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
        r"\end{table}",
        r"\end{document}",
        "",
    ]
    path.write_text("\n".join(lines))


def print_summary(rows):
    print("CTV all-results summary")
    print("method,dice,unseen_dice,hd95,asd")
    for row in rows:
        print(f"{row['method']},{row['dice']},{row['unseen_dice']},{row['hd95']},{row['asd']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_csv", default=str(ROOT / "reports" / "ctv_all_experiment_results.csv"))
    parser.add_argument("--out_tex", default=str(ROOT / "reports" / "ctv_all_experiment_results.tex"))
    args = parser.parse_args()

    rows = collect_rows()
    write_csv(Path(args.out_csv), rows)
    write_tex(Path(args.out_tex), rows)
    print("Wrote", args.out_csv)
    print("Wrote", args.out_tex)
    print("Rows:", len(rows))
    print_summary(rows)


if __name__ == "__main__":
    main()
