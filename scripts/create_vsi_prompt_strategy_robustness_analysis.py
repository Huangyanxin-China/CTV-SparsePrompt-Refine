#!/usr/bin/env python3
"""Create prompt-placement robustness outputs for the VSI manuscript."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "method_validation_ablation_suite" / "summary.csv"
OUT_CSV = ROOT / "reports" / "vsi_prompt_strategy_robustness_20260531.csv"
OUT_MD = ROOT / "reports" / "vsi_prompt_strategy_robustness_20260531.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "prompt_strategy_robustness.tex"

STRATEGY_LABELS = {
    "boundary_focused": "Boundary-focused",
    "even_nonempty": "Even non-empty",
    "max_area_anchors": "Max-area anchors",
}


def metric_cell(row: pd.Series) -> str:
    return f"{row['dice_mean']:.3f} +/- {row['dice_std']:.3f}; unseen {row['dice_unseen_slices_mean']:.3f}"


def tex_metric_cell(row: pd.Series) -> str:
    return (
        rf"${row['dice_mean']:.3f} \pm {row['dice_std']:.3f}$"
        + rf" ({row['dice_unseen_slices_mean']:.3f})"
    )


def make_outputs() -> pd.DataFrame:
    df = pd.read_csv(SOURCE)
    sdf = df[
        (df["profile"] == "mild_expanded")
        & (df["oar_mode"] == "pred_spinal")
        & (df["method"] == "sdf_base")
    ].copy()
    sdf = sdf.sort_values(["k", "strategy", "experiment"]).drop_duplicates(["k", "strategy"], keep="last")

    rows = []
    for k in [3, 5, 7]:
        by_strategy = sdf[sdf["k"] == k].set_index("strategy")
        dice_values = by_strategy["dice_mean"]
        row = {"k": k, "dice_range": float(dice_values.max() - dice_values.min())}
        row["best_strategy"] = STRATEGY_LABELS[str(dice_values.idxmax())]
        for strategy, label in STRATEGY_LABELS.items():
            metrics = by_strategy.loc[strategy]
            row[f"{strategy}_dice_mean"] = metrics["dice_mean"]
            row[f"{strategy}_dice_std"] = metrics["dice_std"]
            row[f"{strategy}_unseen_mean"] = metrics["dice_unseen_slices_mean"]
            row[f"{strategy}_unseen_std"] = metrics["dice_unseen_slices_std"]
        rows.append(row)

    out = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    md_lines = [
        "# VSI Prompt-Placement Robustness Analysis",
        "",
        f"Source: `{SOURCE.relative_to(ROOT)}`",
        "",
        "This analysis uses the mild-expanded profile, predicted-spinal OAR mode, and deployable SDF-base method. Values report Dice mean +/- SD and unseen-slice Dice mean.",
        "",
        "| K | Boundary-focused | Even non-empty | Max-area anchors | Dice range | Best strategy |",
        "| ---: | --- | --- | --- | ---: | --- |",
    ]
    for k in [3, 5, 7]:
        by_strategy = sdf[sdf["k"] == k].set_index("strategy")
        row = out[out["k"] == k].iloc[0]
        md_lines.append(
            f"| {k} | {metric_cell(by_strategy.loc['boundary_focused'])} | "
            f"{metric_cell(by_strategy.loc['even_nonempty'])} | "
            f"{metric_cell(by_strategy.loc['max_area_anchors'])} | "
            f"{row['dice_range']:.3f} | {row['best_strategy']} |"
        )
    md_lines.extend(
        [
            "",
            "Interpretation: prompt placement matters most at K=3. By K=7, the across-strategy Dice range is small, supporting the use of even non-empty prompts as the primary setting while retaining prompt placement as a clinically relevant review variable.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(md_lines))

    tex_lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Prompt-placement robustness of SDF sparse-prompt completion under the mild-expanded profile with predicted-spinal OAR mode. Each cell reports Dice mean $\pm$ SD with unseen-slice Dice in parentheses.}",
        r"\label{tab:prompt-strategy-robustness}",
        r"\begin{tabular}{ccccc}",
        r"\toprule",
        r"$K$ & Boundary-focused & Even non-empty & Max-area anchors & Dice range \\",
        r"\midrule",
    ]
    for k in [3, 5, 7]:
        by_strategy = sdf[sdf["k"] == k].set_index("strategy")
        row = out[out["k"] == k].iloc[0]
        tex_lines.append(
            rf"{k} & "
            rf"{tex_metric_cell(by_strategy.loc['boundary_focused'])} & "
            rf"{tex_metric_cell(by_strategy.loc['even_nonempty'])} & "
            rf"{tex_metric_cell(by_strategy.loc['max_area_anchors'])} & "
            rf"${row['dice_range']:.3f}$ \\"
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
