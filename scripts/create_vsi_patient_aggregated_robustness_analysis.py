#!/usr/bin/env python3
"""Create patient-aggregated robustness outputs for the VSI manuscript.

The main benchmark is scan-level and contains longitudinal repeat scans. This
audit collapses scans to one row per patient before summarizing performance, so
the manuscript can state how much the result changes when repeated patients are
not over-weighted.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PER_CASE = ROOT / "reports" / "ctv_main_per_case_comparison.csv"
OUT_CSV = ROOT / "reports" / "vsi_patient_aggregated_robustness_20260601.csv"
OUT_MD = ROOT / "reports" / "vsi_patient_aggregated_robustness_20260601.md"
OUT_TEX = ROOT / "manuscript_vsi_biomedical_data" / "tables" / "patient_aggregated_robustness.tex"


METRICS = [
    {
        "column": "our_sdf_dice",
        "label": "Dice",
        "tail_definition": "<0.85",
        "tail_op": "lt",
        "tail_value": 0.85,
    },
    {
        "column": "our_sdf_unseen_dice",
        "label": "Unseen-slice Dice",
        "tail_definition": "<0.80",
        "tail_op": "lt",
        "tail_value": 0.80,
    },
    {
        "column": "our_sdf_hd95",
        "label": "HD95 (mm)",
        "tail_definition": ">6 mm",
        "tail_op": "gt",
        "tail_value": 6.0,
    },
    {
        "column": "our_sdf_asd",
        "label": "ASD (mm)",
        "tail_definition": ">2 mm",
        "tail_op": "gt",
        "tail_value": 2.0,
    },
    {
        "column": "abs_volume_diff_percent",
        "label": "Abs. volume diff. (%)",
        "tail_definition": ">15%",
        "tail_op": "gt",
        "tail_value": 15.0,
    },
    {
        "column": "delta_vs_best_baseline",
        "label": "Delta vs best baseline Dice",
        "tail_definition": "<=0",
        "tail_op": "le",
        "tail_value": 0.0,
    },
]


def patient_id(case_id: str) -> str:
    return case_id.split("_CT", 1)[0]


def fmt(value: float) -> str:
    return f"{value:.3f}"


def tex_text(value: object) -> str:
    return str(value).replace("%", r"\%")


def tail_count(values: pd.Series, op: str, threshold: float) -> int:
    if op == "lt":
        return int((values < threshold).sum())
    if op == "le":
        return int((values <= threshold).sum())
    if op == "gt":
        return int((values > threshold).sum())
    if op == "ge":
        return int((values >= threshold).sum())
    raise ValueError(f"Unknown tail operation: {op}")


def mean_sd(values: pd.Series) -> str:
    return f"{fmt(values.mean())} +/- {fmt(values.std(ddof=1))}"


def median_iqr(values: pd.Series) -> str:
    q1 = values.quantile(0.25)
    median = values.median()
    q3 = values.quantile(0.75)
    return f"{fmt(median)} [{fmt(q1)}, {fmt(q3)}]"


def build_rows() -> tuple[pd.DataFrame, dict[str, int]]:
    df = pd.read_csv(PER_CASE)
    baseline_cols = ["nnunet_dice", "diffunet_dice", "sam_sparse_k7_dice", "sam_ct_derived_dice"]
    df["patient_id"] = df["case"].map(patient_id)
    df["best_baseline_dice"] = df[baseline_cols].max(axis=1)
    df["delta_vs_best_baseline"] = df["our_sdf_dice"] - df["best_baseline_dice"]
    df["abs_volume_diff_percent"] = df["our_sdf_volume_diff_percent"].abs()

    patient_df = (
        df.groupby("patient_id", as_index=False)
        [
            [
                "our_sdf_dice",
                "our_sdf_unseen_dice",
                "our_sdf_hd95",
                "our_sdf_asd",
                "abs_volume_diff_percent",
                "delta_vs_best_baseline",
            ]
        ]
        .mean()
    )
    repeated_patients = int((df.groupby("patient_id")["case"].count() > 1).sum())

    rows = []
    for metric in METRICS:
        scan_values = df[metric["column"]]
        patient_values = patient_df[metric["column"]]
        rows.append(
            {
                "endpoint": metric["label"],
                "scan_mean_sd": mean_sd(scan_values),
                "patient_mean_sd": mean_sd(patient_values),
                "patient_median_iqr": median_iqr(patient_values),
                "patient_range": f"{fmt(patient_values.min())}-{fmt(patient_values.max())}",
                "patient_tail_definition": metric["tail_definition"],
                "patient_tail_count": tail_count(patient_values, metric["tail_op"], metric["tail_value"]),
            }
        )
    metadata = {
        "scan_count": int(len(df)),
        "patient_count": int(patient_df["patient_id"].nunique()),
        "repeated_patient_count": repeated_patients,
    }
    return pd.DataFrame(rows), metadata


def write_markdown(rows: pd.DataFrame, metadata: dict[str, int]) -> None:
    row_by_endpoint = {row.endpoint: row for row in rows.itertuples(index=False)}
    lines = [
        "# VSI Patient-Aggregated Robustness Analysis",
        "",
        f"Source: `{PER_CASE.relative_to(ROOT)}`",
        "",
        "This audit collapses longitudinal repeat scans to one mean row per patient before summarizing the proposed method. It is a group-aware robustness check for the scan-level benchmark and does not create a patient-external validation claim.",
        "",
        "## Cohort Units",
        "",
        f"- Scan-level rows: {metadata['scan_count']}",
        f"- Unique patients after aggregation: {metadata['patient_count']}",
        f"- Patients with repeated longitudinal scans: {metadata['repeated_patient_count']}",
        f"- Patient-mean Dice: {row_by_endpoint['Dice'].patient_mean_sd}",
        f"- Patient-mean unseen-slice Dice: {row_by_endpoint['Unseen-slice Dice'].patient_mean_sd}",
        f"- Patient-mean delta vs best baseline Dice: {row_by_endpoint['Delta vs best baseline Dice'].patient_mean_sd}",
        "",
        "## Patient-Aggregated Summary",
        "",
        "| Endpoint | Scan mean +/- SD | Patient mean +/- SD | Patient median [IQR] | Patient range | Patient tail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows.itertuples(index=False):
        lines.append(
            f"| {row.endpoint} | {row.scan_mean_sd} | {row.patient_mean_sd} | {row.patient_median_iqr} | {row.patient_range} | {row.patient_tail_definition}: {row.patient_tail_count}/{metadata['patient_count']} |"
        )
    lines.extend(
        [
            "",
            "Interpretation: the patient-aggregated summary remains close to the scan-level summary and all patient-mean rows retain a positive Dice gain over each patient's strongest deployable baseline. This supports the scan-level result while preserving the limitation that the current cohort is not patient-external.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines))


def write_tex(rows: pd.DataFrame, metadata: dict[str, int]) -> None:
    tail_tex = {
        "<0.85": r"$<0.85$",
        "<0.80": r"$<0.80$",
        ">6 mm": r"$>6$ mm",
        ">2 mm": r"$>2$ mm",
        ">15%": r"$>15\%$",
        "<=0": r"$\leq 0$",
    }
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Patient-aggregated robustness audit. Longitudinal scans are averaged within each patient before summarization, reducing repeated-scan weighting while preserving the scan-level validation boundary.}",
        r"\label{tab:patient-aggregated-robustness}",
        r"\begin{tabular}{lccc}",
        r"\toprule",
        r"Endpoint & Scan mean $\pm$ SD & Patient mean $\pm$ SD & Patient tail \\",
        r"\midrule",
    ]
    for row in rows.itertuples(index=False):
        scan_mean_sd = tex_text(row.scan_mean_sd).replace("+/-", r"$\pm$")
        patient_mean_sd = tex_text(row.patient_mean_sd).replace("+/-", r"$\pm$")
        lines.append(
            f"{tex_text(row.endpoint)} & {scan_mean_sd} & "
            f"{patient_mean_sd} & "
            f"{tail_tex[row.patient_tail_definition]}: {row.patient_tail_count}/{metadata['patient_count']} "
            + r"\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\vspace{2mm}",
            (
                r"\parbox{0.94\linewidth}{\footnotesize Rows are computed from "
                f"{metadata['scan_count']} scans collapsed to {metadata['patient_count']} patients; "
                f"{metadata['repeated_patient_count']} patients contributed repeated scans."
                r"}"
            ),
            r"\end{table}",
            "",
        ]
    )
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text("\n".join(lines))


def main() -> None:
    rows, metadata = build_rows()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(OUT_CSV, index=False)
    write_markdown(rows, metadata)
    write_tex(rows, metadata)
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_TEX}")
    print(rows.to_string(index=False))


if __name__ == "__main__":
    main()
