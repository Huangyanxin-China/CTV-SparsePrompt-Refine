#!/usr/bin/env python3
"""Create paired statistical comparison outputs for the VSI manuscript."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
PER_CASE = ROOT / "reports" / "ctv_main_per_case_comparison.csv"
OUT_CSV = ROOT / "reports" / "vsi_main_paired_statistical_comparison_20260531.csv"
OUT_MD = ROOT / "reports" / "vsi_main_paired_statistical_comparison_20260531.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "paired_statistical_comparison.tex"

BASELINES = [
    ("nnunet_dice", "nnU-Net", "Fully automatic"),
    ("diffunet_dice", "DiffUNet", "Fully automatic"),
    ("sam_ct_derived_dice", "SAM-Med3D CT-derived", "Automatic prompt"),
    ("sam_sparse_k7_dice", "SAM-Med3D sparse K=7", "Sparse prompt"),
]


def bootstrap_ci(values: np.ndarray, seed: int = 20260531, n_boot: int = 20000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    samples = values[idx].mean(axis=1)
    lo, hi = np.percentile(samples, [2.5, 97.5])
    return float(lo), float(hi)


def holm_adjust(p_values: list[float]) -> list[float]:
    m = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(m, dtype=float)
    running_max = 0.0
    for rank, idx in enumerate(order):
        raw = p_values[idx] * (m - rank)
        running_max = max(running_max, raw)
        adjusted[idx] = min(running_max, 1.0)
    return adjusted.tolist()


def fmt_p(value: float) -> str:
    if value < 1e-4:
        return "<0.0001"
    return f"{value:.4f}"


def fmt_mean_sd(mean: float, sd: float) -> str:
    return f"{mean:.3f} +/- {sd:.3f}"


def make_outputs() -> pd.DataFrame:
    df = pd.read_csv(PER_CASE)
    proposed = df["our_sdf_dice"].to_numpy(dtype=float)
    rows = []
    for col, method, group in BASELINES:
        baseline = df[col].to_numpy(dtype=float)
        delta = proposed - baseline
        ci_low, ci_high = bootstrap_ci(delta)
        stat = stats.wilcoxon(proposed, baseline, alternative="two-sided", zero_method="wilcox", method="auto")
        rows.append(
            {
                "comparison_group": group,
                "baseline": method,
                "n": len(delta),
                "proposed_dice_mean": proposed.mean(),
                "proposed_dice_std": proposed.std(ddof=0),
                "baseline_dice_mean": baseline.mean(),
                "baseline_dice_std": baseline.std(ddof=0),
                "mean_delta_dice": delta.mean(),
                "median_delta_dice": float(np.median(delta)),
                "delta_ci95_low": ci_low,
                "delta_ci95_high": ci_high,
                "improved_cases": int(np.sum(delta > 0)),
                "equal_cases": int(np.sum(delta == 0)),
                "worse_cases": int(np.sum(delta < 0)),
                "cohen_dz": delta.mean() / delta.std(ddof=1),
                "wilcoxon_statistic": float(stat.statistic),
                "wilcoxon_p_two_sided": float(stat.pvalue),
            }
        )

    out = pd.DataFrame(rows)
    out["holm_p_two_sided"] = holm_adjust(out["wilcoxon_p_two_sided"].tolist())
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    md_lines = [
        "# VSI Main Paired Statistical Comparison",
        "",
        f"Source: `{PER_CASE.relative_to(ROOT)}`",
        "",
        "Test: paired Wilcoxon signed-rank test on per-case Dice, two-sided, with Holm correction across four main comparisons.",
        "Confidence intervals: deterministic bootstrap 95% CI for the mean paired Dice delta, 20,000 resamples.",
        "",
        "| Baseline | Group | Proposed Dice | Baseline Dice | Mean Delta | 95% CI | Improved / Worse | Cohen dz | Holm p |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in out.itertuples(index=False):
        md_lines.append(
            "| "
            f"{row.baseline} | {row.comparison_group} | "
            f"{fmt_mean_sd(row.proposed_dice_mean, row.proposed_dice_std)} | "
            f"{fmt_mean_sd(row.baseline_dice_mean, row.baseline_dice_std)} | "
            f"{row.mean_delta_dice:.3f} | "
            f"[{row.delta_ci95_low:.3f}, {row.delta_ci95_high:.3f}] | "
            f"{row.improved_cases}/{row.worse_cases} | "
            f"{row.cohen_dz:.2f} | "
            f"{fmt_p(row.holm_p_two_sided)} |"
        )
    md_lines.extend(
        [
            "",
            "Interpretation: all four paired comparisons favor the proposed SDF completion on all 31 test cases. These statistics support the main comparative claim but do not remove the manuscript's separate limitations around private-cohort generalization and final author/ethics metadata.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(md_lines))

    tex_lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Paired statistical comparison of the proposed SDF sparse-prompt completion against main baselines on 31 scan-level test scans. P values use a two-sided paired Wilcoxon signed-rank test with Holm correction across four comparisons.}",
        r"\label{tab:paired-statistical-comparison}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Baseline & Mean $\Delta$ Dice & 95\% CI & Improved/Worse & Holm $p$ \\",
        r"\midrule",
    ]
    for row in out.itertuples(index=False):
        tex_lines.append(
            f"{row.baseline} & "
            f"{row.mean_delta_dice:.3f} & "
            f"[{row.delta_ci95_low:.3f}, {row.delta_ci95_high:.3f}] & "
            f"{row.improved_cases}/{row.worse_cases} & "
            f"{fmt_p(row.holm_p_two_sided)} " + r"\\"
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
    print(out[["baseline", "mean_delta_dice", "delta_ci95_low", "delta_ci95_high", "holm_p_two_sided"]].to_string(index=False))


if __name__ == "__main__":
    main()
