#!/usr/bin/env python3
"""Create OAR hard-constraint sensitivity outputs for the VSI manuscript."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "method_validation_ablation_suite" / "summary.csv"
OUT_CSV = ROOT / "reports" / "vsi_oar_constraint_sensitivity_20260531.csv"
OUT_MD = ROOT / "reports" / "vsi_oar_constraint_sensitivity_20260531.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "oar_constraint_sensitivity.tex"

OAR_LABELS = {
    "none": "None",
    "gt_spinal": "GT spinal",
    "gt_spinal_margin3": "GT spinal +3 mm",
    "pred_spinal": "Pred spinal",
    "pred_spinal_margin3": "Pred spinal +3 mm",
}

METHOD_LABELS = {
    "sdf_base": "SDF base",
    "core_only": "Core only",
    "envelope": "Envelope",
}


def metric(row: pd.Series) -> str:
    return f"{row['dice_mean']:.3f} +/- {row['dice_std']:.3f}; unseen {row['dice_unseen_slices_mean']:.3f}"


def tex_metric(row: pd.Series) -> str:
    return rf"${row['dice_mean']:.3f} \pm {row['dice_std']:.3f}$ ({row['dice_unseen_slices_mean']:.3f})"


def make_outputs() -> pd.DataFrame:
    df = pd.read_csv(SOURCE)
    sub = df[
        (df["experiment"] == "oar_ablation")
        & (df["profile"] == "current")
        & (df["k"] == 7)
        & (df["strategy"] == "even_nonempty")
        & (df["method"].isin(METHOD_LABELS))
        & (df["oar_mode"].isin(OAR_LABELS))
    ].copy()
    sub = sub.sort_values(["oar_mode", "method", "experiment"]).drop_duplicates(["oar_mode", "method"], keep="last")
    sub["oar_label"] = sub["oar_mode"].map(OAR_LABELS)
    sub["method_label"] = sub["method"].map(METHOD_LABELS)

    rows = []
    for oar_mode in OAR_LABELS:
        by_method = sub[sub["oar_mode"] == oar_mode].set_index("method")
        row = {"oar_mode": oar_mode, "oar_label": OAR_LABELS[oar_mode]}
        for method in METHOD_LABELS:
            metrics = by_method.loc[method]
            row[f"{method}_dice_mean"] = metrics["dice_mean"]
            row[f"{method}_dice_std"] = metrics["dice_std"]
            row[f"{method}_unseen_mean"] = metrics["dice_unseen_slices_mean"]
            row[f"{method}_unseen_std"] = metrics["dice_unseen_slices_std"]
        rows.append(row)
    out = pd.DataFrame(rows)

    range_rows = []
    for method in METHOD_LABELS:
        values = sub[sub["method"] == method]["dice_mean"]
        range_rows.append({"method": method, "method_label": METHOD_LABELS[method], "dice_range": values.max() - values.min()})
    ranges = pd.DataFrame(range_rows)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    md_lines = [
        "# VSI OAR Constraint Sensitivity Analysis",
        "",
        f"Source: `{SOURCE.relative_to(ROOT)}`",
        "",
        "This analysis uses the current profile, K=7, even-nonempty prompt placement, and the OAR-ablation experiment. Values report Dice mean +/- SD and unseen-slice Dice mean.",
        "",
        "| OAR mode | SDF base | Core only | Envelope |",
        "| --- | --- | --- | --- |",
    ]
    for oar_mode in OAR_LABELS:
        by_method = sub[sub["oar_mode"] == oar_mode].set_index("method")
        md_lines.append(
            f"| {OAR_LABELS[oar_mode]} | {metric(by_method.loc['sdf_base'])} | "
            f"{metric(by_method.loc['core_only'])} | {metric(by_method.loc['envelope'])} |"
        )
    md_lines.extend(["", "## Across-OAR Dice Ranges", "", "| Method | Dice range |", "| --- | ---: |"])
    for row in ranges.itertuples(index=False):
        md_lines.append(f"| {row.method_label} | {row.dice_range:.6f} |")
    md_lines.extend(
        [
            "",
            "Interpretation: spinal-cord hard-exclusion mode does not measurably change the current K=7 SDF/core/envelope results. The anatomy channel is therefore best described as a constraint and audit channel, not as the primary driver of the reported Dice gain.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(md_lines))

    tex_lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{OAR hard-constraint sensitivity for the current K=7 even-nonempty setting. Each cell reports Dice mean $\pm$ SD with unseen-slice Dice in parentheses.}",
        r"\label{tab:oar-constraint-sensitivity}",
        r"\begin{tabular}{lccc}",
        r"\toprule",
        r"OAR mode & SDF base & Core only & Envelope \\",
        r"\midrule",
    ]
    for oar_mode in OAR_LABELS:
        by_method = sub[sub["oar_mode"] == oar_mode].set_index("method")
        tex_lines.append(
            f"{OAR_LABELS[oar_mode]} & "
            f"{tex_metric(by_method.loc['sdf_base'])} & "
            f"{tex_metric(by_method.loc['core_only'])} & "
            f"{tex_metric(by_method.loc['envelope'])} "
            + r"\\"
        )
    tex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text("\n".join(tex_lines))
    return out


def main() -> None:
    out = make_outputs()
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_TEX}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
