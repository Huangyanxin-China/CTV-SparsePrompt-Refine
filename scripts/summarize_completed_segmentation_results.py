#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
from collections import defaultdict

import numpy as np


TASK_CLASS_NAMES = {
    "ctv": {1: "CTV"},
    "oar": {1: "Lung", 2: "Heart", 3: "Spinal cord", 4: "Esophagus"},
}

METHOD_NAMES = {
    "diffunet": "DiffUNet",
    "sammed3d_click10": "SAM-Med3D (10-click prompt)",
    "sammed3d_nonoracle_ct_heuristic_click1": "SAM-Med3D (CT-derived prompt)",
}


def mean_std(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return None, None, 0
    return float(arr.mean()), float(arr.std()), int(arr.size)


def fmt_mean_std(mean, std, digits=3):
    if mean is None:
        return "--"
    if std is None:
        return f"{mean:.{digits}f}"
    return f"{mean:.{digits}f} $\\pm$ {std:.{digits}f}"


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


def read_external_test_rows(metrics_root):
    rows = []
    for path in sorted(glob.glob(os.path.join(metrics_root, "*", "*", "summary.json"))):
        parts = path.split(os.sep)
        method_key = parts[-3]
        task = parts[-2]
        if task not in TASK_CLASS_NAMES:
            continue
        with open(path) as f:
            summary = json.load(f)
        method = METHOD_NAMES.get(method_key, method_key)
        for cls_str, metrics in sorted(summary.get("per_class", {}).items(), key=lambda x: int(x[0])):
            cls = int(cls_str)
            names = TASK_CLASS_NAMES[task]
            rows.append({
                "task": task.upper(),
                "method": method,
                "class": names.get(cls, f"Class {cls}"),
                "n": metrics.get("dice", {}).get("n", 0),
                "dice": fmt_mean_std(metrics.get("dice", {}).get("mean"), metrics.get("dice", {}).get("std")),
                "hd95": fmt_mean_std(metrics.get("hd95", {}).get("mean"), metrics.get("hd95", {}).get("std"), 2),
                "asd": fmt_mean_std(metrics.get("asd", {}).get("mean"), metrics.get("asd", {}).get("std"), 2),
                "vdiff": fmt_mean_std(
                    metrics.get("volume_diff_percent", {}).get("mean"),
                    metrics.get("volume_diff_percent", {}).get("std"),
                    1,
                ),
            })
    return rows


def dataset_to_task(path):
    if "Dataset014" in path:
        return "oar"
    if "Dataset015" in path:
        return "ctv"
    return None


def read_nnunet_validation_rows(project_root):
    summaries = sorted(glob.glob(os.path.join(
        project_root,
        "nnunet_runs",
        "*",
        "results",
        "*",
        "*",
        "fold_*",
        "validation",
        "summary.json",
    )))
    grouped = defaultdict(lambda: defaultdict(list))
    folds = defaultdict(set)

    for path in summaries:
        task = dataset_to_task(path)
        if task is None:
            continue
        fold_match = re.search(r"fold_(\d+)", path)
        fold = int(fold_match.group(1)) if fold_match else -1
        folds[task].add(fold)
        with open(path) as f:
            summary = json.load(f)
        for case in summary.get("metric_per_case", []):
            for cls_str, metrics in case.get("metrics", {}).items():
                grouped[task][int(cls_str)].append(metrics.get("Dice", float("nan")))

    rows = []
    for task, cls_values in sorted(grouped.items()):
        fold_text = ",".join(str(f) for f in sorted(folds[task]))
        for cls, values in sorted(cls_values.items()):
            mean, std, n = mean_std(values)
            rows.append({
                "task": task.upper(),
                "method": "nnU-Net 3d_fullres",
                "folds": fold_text,
                "class": TASK_CLASS_NAMES[task].get(cls, f"Class {cls}"),
                "n": n,
                "dice": fmt_mean_std(mean, std),
            })
    return rows


def make_test_table(rows):
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Completed independent test-set segmentation results.}",
        r"\label{tab:completed-test-results}",
        r"\begin{tabular}{llllrrrr}",
        r"\toprule",
        r"Task & Method & Class & $n$ & Dice & HD95 (mm) & ASD (mm) & Volume diff. (\%) \\",
        r"\midrule",
    ]
    for r in rows:
        lines.append(
            f"{tex_escape(r['task'])} & {tex_escape(r['method'])} & {tex_escape(r['class'])} & "
            f"{r['n']} & {r['dice']} & {r['hd95']} & {r['asd']} & {r['vdiff']} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def make_val_table(rows):
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Completed nnU-Net internal validation results. These rows are not independent test-set results.}",
        r"\label{tab:completed-nnunet-validation-results}",
        r"\begin{tabular}{lllllr}",
        r"\toprule",
        r"Task & Method & Completed folds & Class & $n$ & Dice \\",
        r"\midrule",
    ]
    for r in rows:
        lines.append(
            f"{tex_escape(r['task'])} & {tex_escape(r['method'])} & {tex_escape(r['folds'])} & "
            f"{tex_escape(r['class'])} & {r['n']} & {r['dice']} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    parser.add_argument("--out_tex", default=None)
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    out_tex = args.out_tex or os.path.join(project_root, "reports", "completed_segmentation_results.tex")
    os.makedirs(os.path.dirname(out_tex), exist_ok=True)

    test_rows = read_external_test_rows(os.path.join(project_root, "external_runs", "metrics"))
    val_rows = read_nnunet_validation_rows(project_root)

    content = "\n".join([
        r"\documentclass{article}",
        r"\usepackage{booktabs}",
        r"\usepackage[margin=1in]{geometry}",
        r"\begin{document}",
        r"\section*{Completed segmentation results}",
        r"Only results with existing metric summaries on disk are included. SAM-Med3D rows use GT-derived prompts and should be interpreted as promptable segmentation results rather than fully automatic segmentation.",
        "",
        make_test_table(test_rows) if test_rows else "No completed independent test-set result was found.",
        "",
        make_val_table(val_rows) if val_rows else "No completed nnU-Net internal validation result was found.",
        "",
        r"\end{document}",
        "",
    ])

    with open(out_tex, "w") as f:
        f.write(content)

    print("Wrote", out_tex)
    print("Independent test rows:", len(test_rows))
    print("nnU-Net validation rows:", len(val_rows))


if __name__ == "__main__":
    main()
