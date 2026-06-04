#!/usr/bin/env python3
import argparse
import glob
import json
import os


TASK_CLASS_NAMES = {
    "ctv": {1: "CTV"},
    "oar": {1: "Lung", 2: "Heart", 3: "Spinal cord", 4: "Esophagus"},
}

METHODS = {
    "diffunet": ("DiffUNet", "No prompt"),
    "nnunet_3d_fullres_folds012_final": ("nnU-Net 3d_fullres folds 0/1/2", "No prompt"),
    "nnunet_3d_fullres_folds234_final": ("nnU-Net 3d_fullres folds 2/3/4", "No prompt"),
    "sammed3d_nonoracle_ct_heuristic_click1": ("SAM-Med3D CT-derived", "Automatic CT prompt"),
}


def fmt_metric(metric, digits):
    mean = metric.get("mean")
    std = metric.get("std")
    if mean is None:
        return "--"
    return f"{mean:.{digits}f} $\\pm$ {std:.{digits}f}" if std is not None else f"{mean:.{digits}f}"


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


def read_rows(metrics_root):
    rows = []
    for path in sorted(glob.glob(os.path.join(metrics_root, "*", "*", "summary.json"))):
        parts = path.split(os.sep)
        method_key = parts[-3]
        task = parts[-2]
        if method_key not in METHODS or task not in TASK_CLASS_NAMES:
            continue
        method, prompt_type = METHODS[method_key]
        with open(path) as f:
            summary = json.load(f)
        for cls_str, metrics in sorted(summary.get("per_class", {}).items(), key=lambda x: int(x[0])):
            cls = int(cls_str)
            dice = metrics.get("dice", {})
            rows.append(
                {
                    "task": task.upper(),
                    "method": method,
                    "prompt_type": prompt_type,
                    "class": TASK_CLASS_NAMES[task].get(cls, f"Class {cls}"),
                    "n": dice.get("n", 0),
                    "dice": fmt_metric(metrics.get("dice", {}), 3),
                    "hd95": fmt_metric(metrics.get("hd95", {}), 2),
                    "asd": fmt_metric(metrics.get("asd", {}), 2),
                    "vdiff": fmt_metric(metrics.get("volume_diff_percent", {}), 1),
                    "source": path,
                    "num_predictions": summary.get("num_predictions", ""),
                }
            )
    return rows


def make_table(rows):
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Dice-only no-clinician-prompt baseline results on the independent test set.}",
        r"\label{tab:no-prompt-baselines}",
        r"\begin{tabular}{llllrr}",
        r"\toprule",
        r"Task & Method & Prompt type & Class & $n$ & Dice \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{tex_escape(row['task'])} & {tex_escape(row['method'])} & "
            f"{tex_escape(row['prompt_type'])} & {tex_escape(row['class'])} & "
            f"{row['n']} & {row['dice']} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    parser.add_argument("--out_tex", default=None)
    parser.add_argument("--out_csv", default=None)
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    rows = read_rows(os.path.join(project_root, "external_runs", "metrics"))

    out_tex = args.out_tex or os.path.join(project_root, "reports", "no_prompt_baseline_results.tex")
    os.makedirs(os.path.dirname(out_tex), exist_ok=True)
    with open(out_tex, "w") as f:
        f.write("\n".join([
            r"\documentclass{article}",
            r"\usepackage{booktabs}",
            r"\usepackage[margin=1in]{geometry}",
            r"\begin{document}",
            r"\section*{No-clinician-prompt baseline results}",
            (
                "This table excludes SAM-Med3D full-GT prompt results. "
                "SAM-Med3D CT-derived uses an automatic CT heuristic prompt and no clinician-provided target prompt."
            ),
            "",
            make_table(rows) if rows else "No completed no-clinician-prompt baseline metrics were found.",
            r"\end{document}",
            "",
        ]))

    out_csv = args.out_csv or os.path.join(project_root, "reports", "no_prompt_baseline_results.csv")
    with open(out_csv, "w") as f:
        fields = ["task", "method", "prompt_type", "class", "n", "dice", "num_predictions", "source"]
        f.write(",".join(fields) + "\n")
        for row in rows:
            f.write(",".join(str(row.get(field, "")).replace(",", ";") for field in fields) + "\n")

    print("Wrote", out_tex)
    print("Wrote", out_csv)
    print("Rows:", len(rows))


if __name__ == "__main__":
    main()
