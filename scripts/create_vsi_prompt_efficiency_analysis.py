#!/usr/bin/env python3
"""Create prompt-efficiency frontier outputs for the VSI manuscript."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "method_validation_ablation_suite" / "summary.csv"
OUT_CSV = ROOT / "reports" / "vsi_prompt_efficiency_frontier_20260531.csv"
OUT_MD = ROOT / "reports" / "vsi_prompt_efficiency_frontier_20260531.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "prompt_efficiency_frontier.tex"


def fmt_delta(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.3f}"


def tex_delta(value: float | None) -> str:
    if value is None:
        return r"--"
    return rf"${value:.3f}$"


def tex_percent(value: float | None) -> str:
    if value is None:
        return r"--"
    return rf"{value:.1f}\%"


def make_outputs() -> pd.DataFrame:
    df = pd.read_csv(SOURCE)
    sub = df[
        (df["profile"] == "mild_expanded")
        & (df["strategy"] == "even_nonempty")
        & (df["oar_mode"] == "pred_spinal")
        & (df["method"].isin(["sdf_base", "oracle_upper_bound"]))
        & (df["k"].isin([3, 5, 7]))
    ].copy()
    sub = sub.sort_values(["k", "method", "experiment"]).drop_duplicates(["k", "method"], keep="last")

    rows = []
    sdf_by_k = sub[sub["method"] == "sdf_base"].set_index("k")
    oracle_by_k = sub[sub["method"] == "oracle_upper_bound"].set_index("k")
    k3_dice = float(sdf_by_k.loc[3, "dice_mean"])
    k7_dice = float(sdf_by_k.loc[7, "dice_mean"])
    total_gain = k7_dice - k3_dice
    k3_gap = float(oracle_by_k.loc[3, "dice_mean"] - sdf_by_k.loc[3, "dice_mean"])
    prev_k: int | None = None
    prev_dice: float | None = None
    prev_unseen: float | None = None

    for k in [3, 5, 7]:
        sdf = sdf_by_k.loc[k]
        oracle = oracle_by_k.loc[k]
        dice = float(sdf["dice_mean"])
        unseen = float(sdf["dice_unseen_slices_mean"])
        oracle_gap = float(oracle["dice_mean"] - dice)
        if prev_k is None:
            marginal_dice = None
            marginal_unseen = None
            marginal_per_prompt = None
        else:
            added_prompts = k - prev_k
            marginal_dice = dice - float(prev_dice)
            marginal_unseen = unseen - float(prev_unseen)
            marginal_per_prompt = marginal_dice / added_prompts
        cumulative_recovered = 0.0 if total_gain == 0 else (dice - k3_dice) / total_gain
        gap_reduction = 0.0 if k3_gap == 0 else (k3_gap - oracle_gap) / k3_gap
        rows.append(
            {
                "k": k,
                "sdf_dice_mean": dice,
                "sdf_dice_std": float(sdf["dice_std"]),
                "sdf_unseen_mean": unseen,
                "sdf_unseen_std": float(sdf["dice_unseen_slices_std"]),
                "oracle_dice_mean": float(oracle["dice_mean"]),
                "oracle_gap": oracle_gap,
                "marginal_dice_gain_vs_previous_k": marginal_dice,
                "marginal_unseen_gain_vs_previous_k": marginal_unseen,
                "marginal_dice_gain_per_added_prompt": marginal_per_prompt,
                "k3_to_k7_dice_gain_recovered_percent": 100.0 * cumulative_recovered,
                "oracle_gap_reduction_from_k3_percent": 100.0 * gap_reduction,
            }
        )
        prev_k = k
        prev_dice = dice
        prev_unseen = unseen

    out = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    md_lines = [
        "# VSI Prompt-Efficiency Frontier",
        "",
        f"Source: `{SOURCE.relative_to(ROOT)}`",
        "",
        "This analysis uses the mild-expanded profile, even-nonempty sparse CTV prompts, predicted-spinal OAR mode, and the deployable SDF-base method. It reports the marginal value of adding prompt slices without reusing ground truth at test time. Oracle rows quantify residual envelope headroom and are not deployable.",
        "",
        "| K | SDF Dice | Unseen Dice | Marginal Dice gain | Dice gain per added prompt | K=3 to K=7 gain recovered | Oracle gap | Oracle-gap reduction from K=3 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in out.itertuples(index=False):
        md_lines.append(
            f"| {row.k} | {row.sdf_dice_mean:.3f} +/- {row.sdf_dice_std:.3f} | "
            f"{row.sdf_unseen_mean:.3f} +/- {row.sdf_unseen_std:.3f} | "
            f"{fmt_delta(row.marginal_dice_gain_vs_previous_k)} | "
            f"{fmt_delta(row.marginal_dice_gain_per_added_prompt)} | "
            f"{row.k3_to_k7_dice_gain_recovered_percent:.1f}% | "
            f"{row.oracle_gap:.3f} | {row.oracle_gap_reduction_from_k3_percent:.1f}% |"
        )
    md_lines.extend(
        [
            "",
            "Interpretation: most of the K=3 to K=7 improvement is recovered by moving from K=3 to K=5. The final two prompt slices still improve the primary K=7 operating point and further shrink oracle headroom, but their marginal Dice gain per added slice is smaller. This supports K=7 as a high-confidence evaluation setting and K=5 as a plausible lower-annotation operating point for future validation.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(md_lines))

    tex_lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Prompt-efficiency frontier for even-nonempty sparse CTV prompts under the mild-expanded profile with predicted-spinal OAR mode. Marginal gain is computed against the previous prompt count; oracle gap is non-deployable headroom.}",
        r"\label{tab:prompt-efficiency-frontier}",
        r"\begin{tabular}{cccccc}",
        r"\toprule",
        r"$K$ & SDF Dice & Marginal Dice & Gain / added slice & Recovered gain & Oracle gap \\",
        r"\midrule",
    ]
    for row in out.itertuples(index=False):
        tex_lines.append(
            rf"{row.k} & "
            rf"${row.sdf_dice_mean:.3f} \pm {row.sdf_dice_std:.3f}$ & "
            rf"{tex_delta(row.marginal_dice_gain_vs_previous_k)} & "
            rf"{tex_delta(row.marginal_dice_gain_per_added_prompt)} & "
            rf"{tex_percent(row.k3_to_k7_dice_gain_recovered_percent)} & "
            rf"${row.oracle_gap:.3f}$ \\"
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
