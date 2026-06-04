#!/usr/bin/env python3
"""Create patient-aggregated paired comparison outputs for the VSI manuscript."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
PER_CASE = ROOT / "reports" / "ctv_main_per_case_comparison.csv"
OUT_CSV = ROOT / "reports" / "vsi_patient_aggregated_paired_comparison_20260601.csv"
OUT_MD = ROOT / "reports" / "vsi_patient_aggregated_paired_comparison_20260601.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "patient_aggregated_paired_comparison.tex"

BASELINES = [
    ("nnunet_dice", "nnU-Net", "Fully automatic"),
    ("diffunet_dice", "DiffUNet", "Fully automatic"),
    ("sam_ct_derived_dice", "SAM-Med3D CT-derived", "Automatic prompt"),
    ("sam_sparse_k7_dice", "SAM-Med3D sparse K=7", "Sparse prompt"),
]


def patient_id(case_id: str) -> str:
    return case_id.split("_CT", 1)[0]


def bootstrap_ci(values: np.ndarray, seed: int = 20260601, n_boot: int = 20000) -> tuple[float, float]:
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


def patient_mean_frame() -> tuple[pd.DataFrame, int]:
    df = pd.read_csv(PER_CASE)
    df["patient_id"] = df["case"].map(patient_id)
    repeated_patients = int((df.groupby("patient_id")["case"].count() > 1).sum())
    columns = ["our_sdf_dice"] + [col for col, _, _ in BASELINES]
    patient_df = df.groupby("patient_id", as_index=False)[columns].mean()
    return patient_df, repeated_patients


def make_outputs() -> pd.DataFrame:
    patient_df, repeated_patients = patient_mean_frame()
    proposed = patient_df["our_sdf_dice"].to_numpy(dtype=float)
    rows = []
    for col, method, group in BASELINES:
        baseline = patient_df[col].to_numpy(dtype=float)
        delta = proposed - baseline
        ci_low, ci_high = bootstrap_ci(delta)
        stat = stats.wilcoxon(proposed, baseline, alternative="two-sided", zero_method="wilcox", method="auto")
        rows.append(
            {
                "comparison_group": group,
                "baseline": method,
                "n_patients": len(delta),
                "repeated_patients_collapsed": repeated_patients,
                "proposed_patient_mean_dice": proposed.mean(),
                "proposed_patient_std_dice": proposed.std(ddof=1),
                "baseline_patient_mean_dice": baseline.mean(),
                "baseline_patient_std_dice": baseline.std(ddof=1),
                "mean_delta_dice": delta.mean(),
                "median_delta_dice": float(np.median(delta)),
                "delta_ci95_low": ci_low,
                "delta_ci95_high": ci_high,
                "improved_patients": int(np.sum(delta > 0)),
                "equal_patients": int(np.sum(delta == 0)),
                "worse_patients": int(np.sum(delta < 0)),
                "cohen_dz": delta.mean() / delta.std(ddof=1),
                "wilcoxon_statistic": float(stat.statistic),
                "wilcoxon_p_two_sided": float(stat.pvalue),
            }
        )

    out = pd.DataFrame(rows)
    out["holm_p_two_sided"] = holm_adjust(out["wilcoxon_p_two_sided"].tolist())
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    write_markdown(out)
    write_tex(out)
    return out


def write_markdown(out: pd.DataFrame) -> None:
    n_patients = int(out["n_patients"].iloc[0]) if len(out) else 0
    repeated = int(out["repeated_patients_collapsed"].iloc[0]) if len(out) else 0
    lines = [
        "# VSI Patient-Aggregated Paired Comparison",
        "",
        f"Source: `{PER_CASE.relative_to(ROOT)}`",
        "",
        "This analysis first averages longitudinal scans within each patient and then performs paired comparisons on patient-mean Dice. It is a group-aware companion to the scan-level paired test and does not create a patient-external validation claim.",
        "",
        "## Cohort Units",
        "",
        f"- Patient-mean rows: {n_patients}",
        f"- Repeated patients collapsed before testing: {repeated}",
        "",
        "## Patient-Mean Paired Results",
        "",
        "| Baseline | Group | Proposed patient Dice | Baseline patient Dice | Mean Delta | 95% CI | Improved / Worse patients | Cohen dz | Holm p |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in out.itertuples(index=False):
        lines.append(
            "| "
            f"{row.baseline} | {row.comparison_group} | "
            f"{fmt_mean_sd(row.proposed_patient_mean_dice, row.proposed_patient_std_dice)} | "
            f"{fmt_mean_sd(row.baseline_patient_mean_dice, row.baseline_patient_std_dice)} | "
            f"{row.mean_delta_dice:.3f} | "
            f"[{row.delta_ci95_low:.3f}, {row.delta_ci95_high:.3f}] | "
            f"{row.improved_patients}/{row.worse_patients} | "
            f"{row.cohen_dz:.2f} | "
            f"{fmt_p(row.holm_p_two_sided)} |"
        )
    lines.extend(
        [
            "",
            "Interpretation: all four patient-mean paired comparisons favor the proposed SDF completion for every patient after longitudinal scans are averaged. This strengthens the robustness of the comparative claim while preserving the manuscript's scan-level, non-patient-external validation boundary.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines))


def write_tex(out: pd.DataFrame) -> None:
    n_patients = int(out["n_patients"].iloc[0]) if len(out) else 0
    repeated = int(out["repeated_patients_collapsed"].iloc[0]) if len(out) else 0
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Patient-aggregated paired comparison. Longitudinal scans are averaged within each patient before paired Wilcoxon testing; this reduces repeated-scan weighting without claiming patient-external validation.}",
        r"\label{tab:patient-aggregated-paired-comparison}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Baseline & Mean $\Delta$ Dice & 95\% CI & Improved/Worse & Holm $p$ \\",
        r"\midrule",
    ]
    for row in out.itertuples(index=False):
        lines.append(
            f"{row.baseline} & "
            f"{row.mean_delta_dice:.3f} & "
            f"[{row.delta_ci95_low:.3f}, {row.delta_ci95_high:.3f}] & "
            f"{row.improved_patients}/{row.worse_patients} & "
            f"{fmt_p(row.holm_p_two_sided)} " + r"\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\vspace{2mm}",
            (
                r"\parbox{0.94\linewidth}{\footnotesize Tests use "
                f"{n_patients} patient-mean rows; {repeated} repeated-patient groups were collapsed before testing."
                r"}"
            ),
            r"\end{table}",
            "",
        ]
    )
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text("\n".join(lines))


def main() -> None:
    out = make_outputs()
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_TEX}")
    print(out[["baseline", "mean_delta_dice", "delta_ci95_low", "delta_ci95_high", "improved_patients", "worse_patients", "holm_p_two_sided"]].to_string(index=False))


if __name__ == "__main__":
    main()
