#!/usr/bin/env python3
"""Create clinical-threshold and failure-mode audit outputs for the VSI manuscript."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PER_CASE = ROOT / "reports" / "ctv_main_per_case_comparison.csv"
OUT_CSV = ROOT / "reports" / "vsi_clinical_threshold_failure_audit_20260531.csv"
OUT_MD = ROOT / "reports" / "vsi_clinical_threshold_failure_audit_20260531.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "clinical_threshold_failure_audit.tex"

N_CASES = 31


def pct(count: int, total: int = N_CASES) -> str:
    return f"{100.0 * count / total:.1f}%"


def pass_cell(mask: pd.Series) -> str:
    count = int(mask.sum())
    return f"{count}/{len(mask)} ({pct(count, len(mask))})"


def md_escape(value: object) -> str:
    return str(value).replace("|", r"\|")


def tex_text(value: object) -> str:
    return str(value).replace("%", r"\%")


def make_outputs() -> pd.DataFrame:
    df = pd.read_csv(PER_CASE)
    baseline_cols = ["nnunet_dice", "diffunet_dice", "sam_sparse_k7_dice", "sam_ct_derived_dice"]
    df["best_deployable_baseline_dice"] = df[baseline_cols].max(axis=1)
    df["abs_volume_diff_percent"] = df["our_sdf_volume_diff_percent"].abs()

    proposed_gates = {
        "Dice >= 0.85": df["our_sdf_dice"] >= 0.85,
        "Dice >= 0.90": df["our_sdf_dice"] >= 0.90,
        "Unseen-slice Dice >= 0.80": df["our_sdf_unseen_dice"] >= 0.80,
        "HD95 <= 6 mm": df["our_sdf_hd95"] <= 6.0,
        "ASD <= 2 mm": df["our_sdf_asd"] <= 2.0,
        "|Volume difference| <= 15%": df["abs_volume_diff_percent"] <= 15.0,
    }
    combined_gate = (
        proposed_gates["Dice >= 0.85"]
        & proposed_gates["Unseen-slice Dice >= 0.80"]
        & proposed_gates["HD95 <= 6 mm"]
        & proposed_gates["ASD <= 2 mm"]
        & proposed_gates["|Volume difference| <= 15%"]
    )

    rows = [
        {
            "endpoint": "CTV overlap",
            "gate": "Dice >= 0.85",
            "proposed_pass": pass_cell(proposed_gates["Dice >= 0.85"]),
            "baseline_comparator": pass_cell(df["best_deployable_baseline_dice"] >= 0.85),
            "tail_count": int((~proposed_gates["Dice >= 0.85"]).sum()),
            "interpretation": "Primary overlap review gate.",
        },
        {
            "endpoint": "High-overlap subset",
            "gate": "Dice >= 0.90",
            "proposed_pass": pass_cell(proposed_gates["Dice >= 0.90"]),
            "baseline_comparator": pass_cell(df["best_deployable_baseline_dice"] >= 0.90),
            "tail_count": int((~proposed_gates["Dice >= 0.90"]).sum()),
            "interpretation": "Stricter overlap gate for high-confidence completions.",
        },
        {
            "endpoint": "Unprompted 3D completion",
            "gate": "Unseen-slice Dice >= 0.80",
            "proposed_pass": pass_cell(proposed_gates["Unseen-slice Dice >= 0.80"]),
            "baseline_comparator": "not comparable",
            "tail_count": int((~proposed_gates["Unseen-slice Dice >= 0.80"]).sum()),
            "interpretation": "Checks completion beyond prompted slices.",
        },
        {
            "endpoint": "Surface outlier control",
            "gate": "HD95 <= 6 mm",
            "proposed_pass": pass_cell(proposed_gates["HD95 <= 6 mm"]),
            "baseline_comparator": "not comparable",
            "tail_count": int((~proposed_gates["HD95 <= 6 mm"]).sum()),
            "interpretation": "Flags large boundary deviations.",
        },
        {
            "endpoint": "Mean surface error",
            "gate": "ASD <= 2 mm",
            "proposed_pass": pass_cell(proposed_gates["ASD <= 2 mm"]),
            "baseline_comparator": "not comparable",
            "tail_count": int((~proposed_gates["ASD <= 2 mm"]).sum()),
            "interpretation": "Flags broad surface mismatch.",
        },
        {
            "endpoint": "Volume agreement",
            "gate": "|Volume difference| <= 15%",
            "proposed_pass": pass_cell(proposed_gates["|Volume difference| <= 15%"]),
            "baseline_comparator": "not comparable",
            "tail_count": int((~proposed_gates["|Volume difference| <= 15%"]).sum()),
            "interpretation": "Flags large under- or over-contouring.",
        },
        {
            "endpoint": "Combined review gate",
            "gate": "Dice >= 0.85, unseen >= 0.80, HD95 <= 6, ASD <= 2, |dV| <= 15%",
            "proposed_pass": pass_cell(combined_gate),
            "baseline_comparator": "not comparable",
            "tail_count": int((~combined_gate).sum()),
            "interpretation": "Cases outside this gate should receive targeted review.",
        },
    ]
    out = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    failure_masks = {
        "Dice < 0.85": ~proposed_gates["Dice >= 0.85"],
        "Unseen-slice Dice < 0.80": ~proposed_gates["Unseen-slice Dice >= 0.80"],
        "HD95 > 6 mm": ~proposed_gates["HD95 <= 6 mm"],
        "ASD > 2 mm": ~proposed_gates["ASD <= 2 mm"],
        "|Volume difference| > 15%": ~proposed_gates["|Volume difference| <= 15%"],
    }
    failed_combined = df.loc[~combined_gate].copy()

    md_lines = [
        "# VSI Clinical Threshold and Failure-Mode Audit",
        "",
        f"Source: `{PER_CASE.relative_to(ROOT)}`",
        "",
        "These thresholds are fixed review gates for manuscript reporting and reviewer triage. They are not claimed as institutionally validated clinical acceptance criteria.",
        "",
        "| Endpoint | Gate | Proposed pass | Comparator pass | Tail count | Interpretation |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for row in out.itertuples(index=False):
        md_lines.append(
            f"| {md_escape(row.endpoint)} | {md_escape(row.gate)} | {md_escape(row.proposed_pass)} | {md_escape(row.baseline_comparator)} | {row.tail_count} | {md_escape(row.interpretation)} |"
        )
    md_lines.extend(
        [
            "",
            "## Failure Mode Counts",
            "",
            "Counts are not mutually exclusive and no case identifiers are reported.",
            "",
            "| Failure mode | Count |",
            "| --- | ---: |",
        ]
    )
    for label, mask in failure_masks.items():
        md_lines.append(f"| {md_escape(label)} | {int(mask.sum())}/{len(mask)} |")
    md_lines.extend(
        [
            f"| Any combined-gate failure | {len(failed_combined)}/{len(df)} |",
            "",
            "## Interpretation",
            "",
            f"- The proposed method passes the primary Dice >= 0.85 gate in {pass_cell(proposed_gates['Dice >= 0.85'])}.",
            f"- Only {pass_cell(df['best_deployable_baseline_dice'] >= 0.85)} of the strongest per-case deployable baseline Dice values reach the same 0.85 gate.",
            f"- The combined review gate is passed in {pass_cell(combined_gate)}.",
            "- The six combined-gate failures are driven by overlapping unseen-slice, surface-distance, and volume-difference tails, supporting final physician review rather than fully automatic use.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(md_lines))

    tex_rows = [
        (
            "CTV overlap",
            r"Dice $\geq 0.85$",
            rows[0]["proposed_pass"],
            rows[0]["baseline_comparator"],
            f"{rows[0]['tail_count']}/31",
        ),
        (
            "High-overlap subset",
            r"Dice $\geq 0.90$",
            rows[1]["proposed_pass"],
            rows[1]["baseline_comparator"],
            f"{rows[1]['tail_count']}/31",
        ),
        (
            "Unprompted completion",
            r"Unseen Dice $\geq 0.80$",
            rows[2]["proposed_pass"],
            "--",
            f"{rows[2]['tail_count']}/31",
        ),
        (
            "Surface outlier",
            r"HD95 $\leq 6$ mm",
            rows[3]["proposed_pass"],
            "--",
            f"{rows[3]['tail_count']}/31",
        ),
        (
            "Mean surface error",
            r"ASD $\leq 2$ mm",
            rows[4]["proposed_pass"],
            "--",
            f"{rows[4]['tail_count']}/31",
        ),
        (
            "Volume agreement",
            r"$|\Delta V| \leq 15\%$",
            rows[5]["proposed_pass"],
            "--",
            f"{rows[5]['tail_count']}/31",
        ),
        (
            "Combined review gate",
            r"All five review gates",
            rows[6]["proposed_pass"],
            "--",
            f"{rows[6]['tail_count']}/31",
        ),
    ]
    tex_lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Clinical-threshold and failure-mode audit for the proposed SDF sparse-prompt completion. Gates are fixed review thresholds for reporting and triage, not institutionally validated clinical acceptance criteria. The baseline comparator is each case's strongest deployable baseline Dice when available.}",
        r"\label{tab:clinical-threshold-audit}",
        r"\begin{tabular}{llccc}",
        r"\toprule",
        r"Endpoint & Gate & Proposed pass & Baseline pass & Tail \\",
        r"\midrule",
    ]
    for endpoint, gate, proposed, baseline, tail in tex_rows:
        tex_lines.append(f"{endpoint} & {gate} & {tex_text(proposed)} & {tex_text(baseline)} & {tail} " + r"\\")
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
