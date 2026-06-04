#!/usr/bin/env python3
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "current_experiment_status_summary.md"


def read_csv(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def as_float(value):
    if value in ("", None):
        return None
    return float(value)


def fmt(value, digits=3):
    value = as_float(value)
    if value is None:
        return "--"
    return f"{value:.{digits}f}"


def main_table(rows):
    keep = [
        "nnU-Net 3d_fullres",
        "DiffUNet",
        "SAM-Med3D CT-derived prompt",
        "SAM-Med3D K=7 sparse prompt",
        "Our SDF propagation K=7",
        "Our core-only refinement",
        "Our HU/support/OAR refinement",
        "Core-envelope envelope",
        "SAM-Med3D full-GT prompt",
        "Core-envelope oracle upper bound",
    ]
    row_by_method = {row["method"]: row for row in rows}
    out = []
    for method in keep:
        row = row_by_method.get(method)
        if row:
            out.append(row)
    return out


def top_rows(rows, predicate, key, n=8):
    selected = [row for row in rows if predicate(row) and row.get(key) not in ("", None)]
    return sorted(selected, key=lambda row: float(row[key]), reverse=True)[:n]


def markdown_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def report_lines():
    lines = []
    lines.append("# Current Experiment Status Summary")
    lines.append("")

    main_path = ROOT / "reports/ctv_all_experiment_results.csv"
    main_rows = read_csv(main_path)
    lines.append("## 1. CTV Baseline And K=7 Main Results")
    lines.append("")
    lines.append(
        markdown_table(
            ["Method", "n", "Dice", "Unseen Dice", "Precision", "Recall", "HD95", "ASD"],
            [
                [
                    row["method"],
                    row["n"],
                    row["dice"],
                    row["unseen_dice"],
                    row["precision"],
                    row["recall"],
                    row["hd95"],
                    row["asd"],
                ]
                for row in main_table(main_rows)
            ],
        )
    )
    lines.append("")

    delta_path = ROOT / "reports/ctv_core_envelope_delta_summary.csv"
    if delta_path.exists():
        delta_rows = read_csv(delta_path)
        lines.append("## 2. Core-Envelope Delta Versus SDF Base")
        lines.append("")
        lines.append(
            markdown_table(
                ["Method", "n", "Mean Delta Dice", "Median Delta Dice", "Improved", "Worse", "Equal"],
                [
                    [
                        row["method"],
                        row["n"],
                        fmt(row["mean_delta_vs_sdf_base"], 6),
                        fmt(row["median_delta_vs_sdf_base"], 6),
                        row["improved_cases"],
                        row["worse_cases"],
                        row["equal_cases"],
                    ]
                    for row in delta_rows
                ],
            )
        )
        lines.append("")

    screen_dir = ROOT / "results/next_sparse_prompt_core_envelope_workflow/screen"
    full_dir = ROOT / "results/next_sparse_prompt_core_envelope_workflow/full_top"
    if screen_dir.exists():
        with (screen_dir / "summary.json").open() as f:
            screen_json = json.load(f)
        screen_rows = read_csv(screen_dir / "summary.csv")
        ranking_rows = read_csv(screen_dir / "oracle_gain_ranking.csv")
        lines.append("## 3. Automated Envelope Screening Status")
        lines.append("")
        lines.append(f"- Screen configs: {screen_json.get('num_configs')}")
        lines.append(f"- Screen metric rows: {screen_json.get('num_rows')}")
        lines.append(f"- Skipped cases: {len(screen_json.get('skipped', []))}")
        lines.append("- Grid: K = 1/3/5/7/9, 5 prompt strategies, 4 envelope profiles.")
        lines.append("")

        lines.append("### Best K=7 Non-Oracle Results By Dice")
        lines.append("")
        best_k7 = top_rows(
            screen_rows,
            lambda row: int(row["k"]) == 7 and row["method"] != "oracle_upper_bound",
            "dice_mean",
            n=8,
        )
        lines.append(
            markdown_table(
                ["Profile", "K", "Strategy", "Method", "Dice", "Unseen Dice", "Precision", "Recall"],
                [
                    [
                        row["profile"],
                        row["k"],
                        row["strategy"],
                        row["method"],
                        fmt(row["dice_mean"]),
                        fmt(row["dice_unseen_slices_mean"]),
                        fmt(row["precision_mean"]),
                        fmt(row["recall_mean"]),
                    ]
                    for row in best_k7
                ],
            )
        )
        lines.append("")

        lines.append("### Best K=7 Oracle-Gain Configs")
        lines.append("")
        k7_gain = [row for row in ranking_rows if int(row["k"]) == 7][:8]
        lines.append(
            markdown_table(
                ["Profile", "K", "Strategy", "Core Dice", "Oracle Dice", "Oracle Gain", "Envelope Recall"],
                [
                    [
                        row["profile"],
                        row["k"],
                        row["strategy"],
                        fmt(row["core_dice"]),
                        fmt(row["oracle_dice"]),
                        fmt(row["oracle_gain_vs_core"]),
                        fmt(row["envelope_recall"]),
                    ]
                    for row in k7_gain
                ],
            )
        )
        lines.append("")

    if full_dir.exists():
        full_rows = read_csv(full_dir / "summary.csv")
        full_top = top_rows(full_rows, lambda row: True, "dice_mean", n=12)
        lines.append("## 4. Full Top Rerun With Surface Metrics")
        lines.append("")
        lines.append(
            markdown_table(
                ["Profile", "K", "Strategy", "Method", "Dice", "Unseen Dice", "HD95", "ASD"],
                [
                    [
                        row["profile"],
                        row["k"],
                        row["strategy"],
                        row["method"],
                        fmt(row["dice_mean"]),
                        fmt(row["dice_unseen_slices_mean"]),
                        fmt(row["hd95_mean"], 2),
                        fmt(row["asd_mean"], 2),
                    ]
                    for row in full_top
                ],
            )
        )
        lines.append("")

    lines.append("## 5. Current Interpretation")
    lines.append("")
    lines.append("- Baseline validation, K=7 SDF pseudo, and current core-envelope refinement have completed on all 31 CTV test cases.")
    lines.append("- The previous locked K=7 result is still the strongest clinically usable result: SDF Dice 0.916, core-only Dice 0.920.")
    lines.append("- The new screening workflow has completed. It confirms that expanded envelopes can open oracle headroom, especially for low-K settings, but the high-recall envelopes themselves are not final predictions.")
    lines.append("- For a fair paper result, choose envelope/profile parameters on validation data, then report one locked final run on the 31-case test set.")
    lines.append("")
    return lines


def main():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(report_lines())
    REPORT.write_text(text)
    print(text)
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
