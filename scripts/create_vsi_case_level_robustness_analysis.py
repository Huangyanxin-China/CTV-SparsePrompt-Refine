#!/usr/bin/env python3
"""Create anonymized case-level robustness outputs for the VSI manuscript."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PER_CASE = ROOT / "reports" / "ctv_main_per_case_comparison.csv"
OUT_CSV = ROOT / "reports" / "vsi_case_level_robustness_20260531.csv"
OUT_MD = ROOT / "reports" / "vsi_case_level_robustness_20260531.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "case_level_robustness.tex"


def tex_text(value: object) -> str:
    return str(value).replace("%", r"\%")


def fmt(value: float) -> str:
    return f"{value:.3f}"


def summary_row(df: pd.DataFrame, column: str, label: str, tail: str, tail_count: int) -> dict[str, str]:
    values = df[column]
    q1 = values.quantile(0.25)
    median = values.median()
    q3 = values.quantile(0.75)
    return {
        "endpoint": label,
        "median_iqr": f"{fmt(median)} [{fmt(q1)}, {fmt(q3)}]",
        "range": f"{fmt(values.min())}-{fmt(values.max())}",
        "tail_definition": tail,
        "tail_count": str(tail_count),
    }


def make_outputs() -> pd.DataFrame:
    df = pd.read_csv(PER_CASE)
    baseline_cols = ["nnunet_dice", "diffunet_dice", "sam_sparse_k7_dice", "sam_ct_derived_dice"]
    df["best_baseline_dice"] = df[baseline_cols].max(axis=1)
    df["delta_vs_best_baseline"] = df["our_sdf_dice"] - df["best_baseline_dice"]
    df["abs_volume_diff_percent"] = df["our_sdf_volume_diff_percent"].abs()

    rows = [
        summary_row(df, "our_sdf_dice", "Dice", "<0.85", int((df["our_sdf_dice"] < 0.85).sum())),
        summary_row(
            df,
            "our_sdf_unseen_dice",
            "Unseen-slice Dice",
            "<0.80",
            int((df["our_sdf_unseen_dice"] < 0.80).sum()),
        ),
        summary_row(df, "our_sdf_hd95", "HD95 (mm)", ">6 mm", int((df["our_sdf_hd95"] > 6.0).sum())),
        summary_row(df, "our_sdf_asd", "ASD (mm)", ">2 mm", int((df["our_sdf_asd"] > 2.0).sum())),
        summary_row(
            df,
            "our_sdf_volume_diff_percent",
            "Volume difference (%)",
            "|diff|>15%",
            int((df["abs_volume_diff_percent"] > 15.0).sum()),
        ),
        summary_row(
            df,
            "delta_vs_best_baseline",
            "Delta vs best baseline Dice",
            "<=0",
            int((df["delta_vs_best_baseline"] <= 0.0).sum()),
        ),
    ]
    out = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    md_lines = [
        "# VSI Case-Level Robustness Analysis",
        "",
        f"Source: `{PER_CASE.relative_to(ROOT)}`",
        "",
        "This anonymized distribution summary avoids reporting case identifiers in the manuscript.",
        "",
        "| Endpoint | Median [IQR] | Range | Tail definition | Tail count |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in out.itertuples(index=False):
        md_lines.append(
            f"| {row.endpoint} | {row.median_iqr} | {row.range} | {row.tail_definition} | {row.tail_count}/31 |"
        )
    md_lines.extend(
        [
            "",
            "Interpretation: the proposed SDF completion has a high median Dice but nonzero tail risk. The lowest-Dice cases are still better than each case's best deployable baseline, while low unseen-slice Dice, high HD95, and large volume difference identify clinically relevant review targets.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(md_lines))

    tex_tail = {
        "<0.85": r"$<0.85$",
        "<0.80": r"$<0.80$",
        ">6 mm": r"$>6$ mm",
        ">2 mm": r"$>2$ mm",
        "|diff|>15%": r"$|\Delta V|>15\%$",
        "<=0": r"$\leq 0$",
    }
    tex_lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Anonymized case-level robustness summary for the proposed SDF sparse-prompt completion on 31 test cases. Tail counts identify clinically relevant review targets without exposing case identifiers.}",
        r"\label{tab:case-level-robustness}",
        r"\begin{tabular}{lccc}",
        r"\toprule",
        r"Endpoint & Median [IQR] & Range & Tail count \\",
        r"\midrule",
    ]
    for row in out.itertuples(index=False):
        tex_lines.append(
            f"{tex_text(row.endpoint)} & {tex_text(row.median_iqr)} & {tex_text(row.range)} & {tex_tail[row.tail_definition]}: {row.tail_count}/31 "
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
