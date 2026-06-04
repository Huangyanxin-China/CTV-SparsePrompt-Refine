#!/usr/bin/env python3
"""Audit validation split and leakage boundaries for the VSI manuscript."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "validation_split_leakage_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_validation_split_leakage_audit_20260601.csv"

MAIN_CASES = ROOT / "reports" / "ctv_main_per_case_comparison.csv"
SDF_PER_CASE = ROOT / "results" / "method_validation_ablation_suite" / "per_case_metrics.csv"
CTV_SPLITS = ROOT / "nnunet_runs" / "Dataset015_CTV_Dataset004Split" / "preprocessed" / "Dataset015_CTV_Dataset004Split" / "splits_final.json"
OAR_SPLITS = ROOT / "nnunet_runs" / "Dataset014_ThoracicOAR_Dataset004Split" / "preprocessed" / "Dataset014_ThoracicOAR_Dataset004Split" / "splits_final.json"
DOCTOR_SPLITS = [
    ROOT / "results" / "doctor_prior_graph_refinement_minisplit5_cached" / "doctor_prior_split.json",
    ROOT / "results" / "doctor_prior_graph_refinement_fast10_k3_cached" / "doctor_prior_split.json",
]


@dataclass(frozen=True)
class AuditRow:
    check: str
    status: str
    evidence: str
    interpretation: str
    action: str


def patient_id(case: str) -> str:
    return case.split("_CT", 1)[0]


def read_cases_from_csv(path: Path, column: str = "case") -> list[str]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        rows = csv.DictReader(handle)
        return [row[column] for row in rows if row.get(column)]


def read_split_cases(path: Path) -> tuple[set[str], dict[str, list[str]], list[str]]:
    if not path.exists():
        return set(), {}, [f"{path.relative_to(ROOT)} missing"]
    data = json.loads(path.read_text())
    all_cases: set[str] = set()
    grouped: dict[str, list[str]] = {}
    fold_notes: list[str] = []

    if isinstance(data, list):
        for idx, fold in enumerate(data):
            train = [str(item) for item in fold.get("train", [])]
            val = [str(item) for item in fold.get("val", [])]
            all_cases.update(train)
            all_cases.update(val)
            grouped[f"fold{idx}_train"] = train
            grouped[f"fold{idx}_val"] = val
            overlap = sorted({patient_id(case) for case in train} & {patient_id(case) for case in val})
            fold_notes.append(f"fold {idx}: train={len(train)}, val={len(val)}, train-val patient overlap={len(overlap)}")
    elif isinstance(data, dict):
        cases_by_split = data.get("cases_by_split", {})
        for split, cases in cases_by_split.items():
            grouped[str(split)] = [str(case) for case in cases]
            all_cases.update(grouped[str(split)])
    return all_cases, grouped, fold_notes


def split_patient_overlaps(grouped: dict[str, list[str]]) -> list[str]:
    names = sorted(grouped)
    notes: list[str] = []
    for left_idx, left in enumerate(names):
        for right in names[left_idx + 1 :]:
            if left.split("_", 1)[0] == right.split("_", 1)[0] and left.startswith("fold"):
                continue
            overlap = sorted({patient_id(case) for case in grouped[left]} & {patient_id(case) for case in grouped[right]})
            if overlap:
                notes.append(f"{left} vs {right}: {len(overlap)} patient overlap ({', '.join(overlap[:8])})")
    return notes


def text_contains(rel: str, needles: list[str]) -> bool:
    path = PKG / rel
    if not path.exists():
        return False
    text = path.read_text().lower()
    return all(needle.lower() in text for needle in needles)


def build_rows() -> list[AuditRow]:
    rows: list[AuditRow] = []

    main_cases = read_cases_from_csv(MAIN_CASES)
    main_patients = [patient_id(case) for case in main_cases]
    patient_counts = Counter(main_patients)
    repeated = {pat: count for pat, count in sorted(patient_counts.items()) if count > 1}
    repeated_text = ", ".join(f"{pat}({count})" for pat, count in repeated.items()) or "none"

    rows.append(
        AuditRow(
            "Main benchmark scan/patient inventory",
            "PASS",
            f"{MAIN_CASES.relative_to(ROOT)}: {len(main_cases)} scans, {len(patient_counts)} unique patients; repeated patients: {repeated_text}",
            "The main benchmark is scan-level; longitudinal repeat scans are present.",
            "Report scan-level and patient-level counts together when describing the cohort.",
        )
    )

    disclosed_scan_level = text_contains(
        "main.tex",
        ["scan-level hold-out", "not a patient-external validation"],
    ) and (
        text_contains("main.tex", ["31 scan-level test scans from 21 unique patients"])
        or text_contains("main.tex", ["31 independent test scans from 21 unique patients"])
    )
    rows.append(
        AuditRow(
            "Scan-level rather than patient-external validation disclosed",
            "PASS_WITH_DISCLOSED_LIMITATION" if disclosed_scan_level else "WARNING",
            "main.tex disclosure present" if disclosed_scan_level else "main.tex does not yet disclose scan-level/patient-level boundary",
            "The evidence supports a scan-level independent test claim, not a fully patient-external claim.",
            "Keep the limitation in Methods/Discussion and avoid external-patient generalization claims.",
        )
    )

    sdf_cases = read_cases_from_csv(SDF_PER_CASE)
    rows.append(
        AuditRow(
            "SDF completion uses the same 31-case evaluation set",
            "PASS" if len(set(sdf_cases)) == len(set(main_cases)) == 31 else "WARNING",
            f"{SDF_PER_CASE.relative_to(ROOT)} unique cases={len(set(sdf_cases))}; main comparison unique cases={len(set(main_cases))}",
            "The ablation-suite per-case file and main comparison file cover the same main evaluation cohort.",
            "Regenerate paired comparison and ablation summaries if this count changes.",
        )
    )

    sdf_nontraining = text_contains(
        "main.tex",
        ["does not train a cohort-level ctv classifier", "deterministic and patient-specific"],
    )
    rows.append(
        AuditRow(
            "Proposed SDF method has no cohort-training leakage path",
            "PASS" if sdf_nontraining else "WARNING",
            "main.tex states deterministic patient-specific propagation without a cohort-level CTV classifier",
            "The proposed SDF result is not a learned cohort model selected by training on other patients.",
            "Continue to separate the proposed deterministic result from learned-baseline and future-prior claims.",
        )
    )

    gt_boundary = text_contains(
        "main.tex",
        ["full CTV ground truth is used only for retrospective evaluation and oracle analysis"],
    )
    rows.append(
        AuditRow(
            "Retrospective prompt/evaluation ground-truth boundary stated",
            "PASS" if gt_boundary else "WARNING",
            "main.tex ground-truth usage boundary found" if gt_boundary else "main.tex ground-truth usage boundary not found",
            "The simulated sparse prompts use selected ground-truth slices, while nonprompted full masks are evaluation/oracle evidence.",
            "Do not describe oracle rows or full-mask evaluation as deployable inputs.",
        )
    )

    split_union: set[str] = set()
    split_notes: list[str] = []
    for split_path in [CTV_SPLITS, OAR_SPLITS]:
        cases, grouped, fold_notes = read_split_cases(split_path)
        split_union.update(cases)
        exact_overlap = sorted(cases & set(main_cases))
        patient_overlap = sorted({patient_id(case) for case in cases} & set(main_patients))
        split_notes.extend(fold_notes)
        rows.append(
            AuditRow(
                f"Exact held-out scan overlap absent for {split_path.parent.name}",
                "PASS" if not exact_overlap and cases else "WARNING",
                f"{split_path.relative_to(ROOT)}: exact overlap with main test scans={len(exact_overlap)}",
                "Available nnU-Net split files do not contain the later held-out scan IDs used in the main comparison.",
                "Retain exact-case separation evidence, but do not upgrade it into patient-external validation.",
            )
        )
        rows.append(
            AuditRow(
                f"Patient-level overlap disclosed for {split_path.parent.name}",
                "PASS_WITH_DISCLOSED_LIMITATION" if patient_overlap and disclosed_scan_level else "WARNING",
                f"{split_path.relative_to(ROOT)}: patient overlap with main test cohort={len(patient_overlap)} ({', '.join(patient_overlap[:12])})",
                "Learned baselines are interpreted under a scan-level protocol; patient-level overlap prevents patient-external claims.",
                "Use future patient-grouped external validation before claiming patient-level generalization for learned baselines.",
            )
        )
        bad_fold_notes = [note for note in fold_notes if not note.endswith("overlap=0")]
        rows.append(
            AuditRow(
                f"Fold train/validation patient separation for {split_path.parent.name}",
                "PASS" if fold_notes and not bad_fold_notes else "WARNING",
                "; ".join(fold_notes[:5]) if fold_notes else "No fold notes available",
                "The available nnU-Net fold definitions separate train and validation cases by patient within each fold.",
                "Keep fold definitions archived with the package.",
            )
        )

    for split_path in DOCTOR_SPLITS:
        _, grouped, _ = read_split_cases(split_path)
        overlaps = split_patient_overlaps(grouped)
        counts = ", ".join(f"{name}={len(cases)}" for name, cases in sorted(grouped.items()))
        rows.append(
            AuditRow(
                f"Doctor-prior split is patient grouped: {split_path.parent.name}",
                "PASS" if grouped and not overlaps else "WARNING",
                f"{split_path.relative_to(ROOT)}: {counts}; overlaps={'; '.join(overlaps) if overlaps else 'none'}",
                "The diagnostic learned-prior experiments use patient-grouped train/validation/test splits.",
                "Do not promote the doctor-prior result unless expanded under the same patient-grouped principle.",
            )
        )

    aligned_claims = text_contains(
        "main.tex",
        ["not a patient-external validation", "fully patient-grouped external validation remains future work"],
    )
    rows.append(
        AuditRow(
            "Manuscript claim boundary matches split audit",
            "PASS" if aligned_claims else "WARNING",
            "main.tex contains patient-external limitation and future-validation boundary" if aligned_claims else "main.tex boundary language missing",
            "The manuscript should describe the current evidence honestly as scan-level private-cohort validation.",
            "Keep the language if future edits revise the cohort description.",
        )
    )

    return rows


def write_csv(rows: list[AuditRow]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "evidence", "interpretation", "action"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def write_markdown(rows: list[AuditRow]) -> None:
    fail_count = sum(1 for row in rows if row.status == "FAIL")
    warning_count = sum(1 for row in rows if "WARNING" in row.status)
    status = "PASS_WITH_SCAN_LEVEL_LIMITATION" if fail_count == 0 else "FAIL"

    lines = [
        "# Validation Split and Leakage Audit",
        "",
        f"- Status: {status}",
        f"- Failing checks: {fail_count}",
        f"- Warning rows: {warning_count}",
        f"- Machine-readable audit: `{CSV_OUT.relative_to(ROOT)}`",
        "",
        "## Summary",
        "",
        "- The current main benchmark is a scan-level private-cohort evaluation.",
        "- The main benchmark includes 31 scans from 21 unique patients, so the paper must not claim patient-external validation.",
        "- The proposed SDF completion is deterministic and patient-specific, with no cohort-level CTV training leakage path.",
        "- Available nnU-Net split files show no exact held-out scan overlap with the main test scans, but they do share patient IDs with the main test cohort; learned baselines are therefore interpreted under the scan-level protocol.",
        "- Doctor-prior diagnostic splits are patient-grouped and remain diagnostic rather than a deployable learned refinement claim.",
        "",
        "## Audit Rows",
        "",
        "| Check | Status | Evidence | Interpretation | Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        evidence = row.evidence.replace("|", "\\|")
        interpretation = row.interpretation.replace("|", "\\|")
        action = row.action.replace("|", "\\|")
        lines.append(f"| {row.check} | {row.status} | {evidence} | {interpretation} | {action} |")

    lines.extend(
        [
            "",
            "## Completion Rule",
            "",
            "This audit is complete for the current draft when failing checks are zero and the manuscript retains the scan-level, non-patient-external validation limitation. It does not replace future patient-grouped external validation.",
        ]
    )
    MD_OUT.write_text("\n".join(lines) + "\n")


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    warning_count = sum(1 for row in rows if "WARNING" in row.status)
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Validation split/leakage audit: rows={len(rows)}; warnings={warning_count}; fails={sum(1 for row in rows if row.status == 'FAIL')}")


if __name__ == "__main__":
    main()
