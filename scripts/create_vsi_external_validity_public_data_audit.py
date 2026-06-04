#!/usr/bin/env python3
"""Audit external-validity and public-data claim boundaries for the VSI paper."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "external_validity_public_data_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_external_validity_public_data_audit_20260531.csv"


@dataclass(frozen=True)
class Evidence:
    rel: str
    line: int
    text: str


@dataclass(frozen=True)
class AuditRow:
    check: str
    status: str
    evidence: list[Evidence]
    interpretation: str


def read_lines(rel: str) -> list[str]:
    path = PKG / rel
    if rel.startswith("reports/"):
        path = ROOT / rel
    if not path.exists():
        return []
    return path.read_text().splitlines()


def read_text(rel: str) -> str:
    return "\n".join(read_lines(rel))


def find_hits(rel: str, needles: list[str]) -> list[Evidence]:
    hits: list[Evidence] = []
    lowered_needles = [needle.lower() for needle in needles]
    for idx, line in enumerate(read_lines(rel), 1):
        lowered_line = line.lower()
        if any(needle in lowered_line for needle in lowered_needles):
            hits.append(Evidence(rel, idx, " ".join(line.strip().split())))
    return hits


def first_hits(rel: str, needles: list[str]) -> list[Evidence]:
    hits: list[Evidence] = []
    for needle in needles:
        found = find_hits(rel, [needle])
        if found:
            hits.append(found[0])
    return hits


def contains_all(rel: str, needles: list[str]) -> bool:
    text = read_text(rel).lower()
    return all(needle.lower() in text for needle in needles)


def contains_any(rel: str, needles: list[str]) -> bool:
    text = read_text(rel).lower()
    return any(needle.lower() in text for needle in needles)


def evidence_cell(evidence: list[Evidence]) -> str:
    if not evidence:
        return "No local evidence found"
    cells = []
    for item in evidence[:6]:
        loc = item.rel if item.line == 0 else f"{item.rel}:{item.line}"
        text = item.text.replace("|", "\\|")
        if len(text) > 130:
            text = text[:127] + "..."
        cells.append(f"`{loc}` {text}")
    if len(evidence) > 6:
        cells.append(f"... plus {len(evidence) - 6} more")
    return "<br>".join(cells)


def risky_public_generalization_hits() -> list[Evidence]:
    risky_phrases = [
        "validated public generalization",
        "publicly generalizable",
        "generalizes across public datasets",
        "state-of-the-art on public datasets",
        "validated on public ctv benchmarks",
        "proves public generalization",
    ]
    hits: list[Evidence] = []
    for rel in [
        "main.tex",
        "cover_letter.txt",
        "source_evidence_manifest.md",
        "peer_review_risk_audit.md",
    ]:
        hits.extend(find_hits(rel, risky_phrases))
    return hits


def risky_fully_automatic_hits() -> list[Evidence]:
    risky_phrases = [
        "proposed fully automatic",
        "fully automatic proposed",
        "fully automated ctv completion",
        "fully automatic ctv completion method",
        "end-to-end automatic ctv completion",
        "without clinician prompts",
        "no clinician prompts",
    ]
    hits: list[Evidence] = []
    for rel in ["main.tex", "cover_letter.txt", "source_evidence_manifest.md"]:
        hits.extend(find_hits(rel, risky_phrases))
    return hits


def row(check: str, ok: bool, evidence: list[Evidence], interpretation: str) -> AuditRow:
    return AuditRow(check=check, status="PASS" if ok else "FAIL", evidence=evidence, interpretation=interpretation)


def build_rows() -> list[AuditRow]:
    rows: list[AuditRow] = []

    private_evidence = []
    private_evidence.extend(
        first_hits(
            "main.tex",
            [
                "private lung proton-therapy CT cohort",
                "31 scan-level test scans from 21 patients",
                "31 scan-level test scans from 21 unique patients",
                "31 independent test scans",
            ],
        )
    )
    private_evidence.extend(first_hits("data_availability_statement.txt", ["private institutional radiotherapy planning data", "cannot be publicly released"]))
    rows.append(
        row(
            "Private institutional cohort disclosed",
            contains_all("main.tex", ["private lung proton-therapy CT cohort"])
            and contains_any(
                "main.tex",
                [
                    "31 scan-level test scans from 21 patients",
                    "31 scan-level test scans from 21 unique patients",
                    "31 independent test scans",
                ],
            )
            and contains_all("data_availability_statement.txt", ["private institutional radiotherapy planning data", "cannot be publicly released"]),
            private_evidence,
            "The validation cohort is identified as private institutional radiotherapy data rather than a public benchmark.",
        )
    )

    public_benchmark_evidence = []
    public_benchmark_evidence.extend(first_hits("main.tex", ["directly matched public benchmark for sparse-prompted radiotherapy CTV completion"]))
    public_benchmark_evidence.extend(first_hits("cover_letter.txt", ["No public CTV prompt-completion dataset is used"]))
    rows.append(
        row(
            "Public benchmark limitation disclosed",
            contains_all("main.tex", ["directly matched public benchmark for sparse-prompted radiotherapy CTV completion"])
            and contains_all("cover_letter.txt", ["No public CTV prompt-completion dataset is used"]),
            public_benchmark_evidence,
            "The paper states that no directly matched public sparse-prompt CTV benchmark is used.",
        )
    )

    cover_dataset_evidence = first_hits(
        "cover_letter.txt",
        ["Which public datasets are used", "private institutional lung proton-therapy CT cohort", "No public CTV prompt-completion dataset is used"],
    )
    rows.append(
        row(
            "Cover letter public-dataset answer present",
            contains_all("cover_letter.txt", ["Which public datasets are used", "No public CTV prompt-completion dataset is used"]),
            cover_dataset_evidence,
            "The cover letter answers the Pattern Recognition public-dataset question without inventing a public benchmark.",
        )
    )

    public_risky_hits = risky_public_generalization_hits()
    public_boundary_evidence = []
    public_boundary_evidence.extend(first_hits("source_evidence_manifest.md", ["Public-dataset generalization"]))
    public_boundary_evidence.extend(first_hits("peer_review_risk_audit.md", ["directly matched public sparse-prompt CTV benchmark is unavailable"]))
    rows.append(
        row(
            "Public generalization claim avoided",
            not public_risky_hits and bool(public_boundary_evidence),
            public_risky_hits or public_boundary_evidence,
            "The package treats public-dataset generalization as unsupported rather than as a proven claim.",
        )
    )

    fully_auto_risky_hits = risky_fully_automatic_hits()
    fully_auto_evidence = []
    fully_auto_evidence.extend(first_hits("peer_review_risk_audit.md", ["not a fully automatic CT-to-CTV segmentation paper"]))
    fully_auto_evidence.extend(first_hits("main.tex", ["sparse-prompted 3D completion", "differs from both fully automatic CT-to-mask segmentation"]))
    rows.append(
        row(
            "Fully automatic CT-to-CTV claim avoided",
            not fully_auto_risky_hits and bool(fully_auto_evidence),
            fully_auto_risky_hits or fully_auto_evidence,
            "The contribution is framed as sparse-prompted completion; fully automatic methods are baselines, not the claimed proposed workflow.",
        )
    )

    test_count_evidence = first_hits(
        "main.tex",
        [
            "31 scan-level test scans from 21 patients",
            "31 scan-level test scans from 21 unique patients",
            "31 scan-level test scans",
            "31 independent test scans",
            "31-case comparison",
        ],
    )
    rows.append(
        row(
            "Scan-level test-set size documented",
            contains_any(
                "main.tex",
                [
                    "31 scan-level test scans from 21 patients",
                    "31 scan-level test scans from 21 unique patients",
                    "31 independent test scans",
                ],
            ),
            test_count_evidence,
            "The main benchmark size is visible in the abstract and methods/results sections.",
        )
    )

    metric_evidence = []
    metric_evidence.extend(first_hits("main.tex", ["Dice similarity coefficient", "unseen-slice Dice", "HD95", "average surface distance", "volume difference"]))
    metric_evidence.extend(first_hits("cover_letter.txt", ["Dice", "unseen-slice Dice", "HD95", "average surface distance", "volume difference"]))
    rows.append(
        row(
            "Validation measures documented",
            contains_all("main.tex", ["Dice similarity coefficient", "unseen-slice Dice", "HD95", "average surface distance", "volume difference"])
            and contains_all("cover_letter.txt", ["Dice", "unseen-slice Dice", "HD95", "average surface distance", "volume difference"]),
            metric_evidence,
            "Overlap, surface-distance, and volume-bias measures are documented for manuscript and cover-letter review.",
        )
    )

    reproducibility_evidence = []
    reproducibility_evidence.extend(first_hits("reproducibility_manifest.md", ["aggregate metrics and scripts", "Private clinical imaging data cannot be redistributed"]))
    reproducibility_evidence.extend(first_hits("data_availability_statement.txt", ["De-identified aggregate metrics", "analysis scripts"]))
    rows.append(
        row(
            "Reproducibility under private-data limits documented",
            contains_all("reproducibility_manifest.md", ["aggregate metrics and scripts", "Private clinical imaging data cannot be redistributed"])
            and contains_all("data_availability_statement.txt", ["aggregate metrics", "analysis scripts"]),
            reproducibility_evidence,
            "The release supports local audit through scripts and aggregate outputs while preserving private-imaging restrictions.",
        )
    )

    source_control_evidence = []
    source_control_evidence.extend(first_hits("source_evidence_manifest.md", ["Public-dataset generalization", "Full-scale learned doctor-prior graph improvement"]))
    source_control_evidence.extend(first_hits("submission_requirements_traceability.md", ["Public generalization claim avoided", "Fully automatic CT-to-CTV claim avoided"]))
    rows.append(
        row(
            "Unsupported claims remain listed as unsupported",
            contains_all("source_evidence_manifest.md", ["Public-dataset generalization", "Full-scale learned doctor-prior graph improvement"])
            and contains_all("submission_requirements_traceability.md", ["Public generalization claim avoided", "Fully automatic CT-to-CTV claim avoided"]),
            source_control_evidence,
            "Claim-control files continue to exclude public generalization and full-scale learned-refinement claims.",
        )
    )

    residual_evidence = []
    residual_evidence.extend(first_hits("peer_review_risk_audit.md", ["Private-data-only validation", "Clinical cohort details need author confirmation"]))
    residual_evidence.extend(first_hits("author_submission_info_needed.md", ["Data sharing", "ethics", "IRB"]))
    rows.append(
        row(
            "External validity residual risk retained",
            contains_all("peer_review_risk_audit.md", ["Private-data-only validation", "Clinical cohort details need author confirmation"]),
            residual_evidence,
            "Single-institution validation and final data-sharing/ethics language remain explicit residual risks.",
        )
    )

    return rows


def write_csv(rows: list[AuditRow]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "evidence", "interpretation"])
        writer.writeheader()
        for item in rows:
            writer.writerow(
                {
                    "check": item.check,
                    "status": item.status,
                    "evidence": " | ".join(
                        f"{e.rel}:{e.line}:{e.text}" if e.line else f"{e.rel}:{e.text}" for e in item.evidence
                    ),
                    "interpretation": item.interpretation,
                }
            )


def write_markdown(rows: list[AuditRow]) -> None:
    fail_count = sum(1 for item in rows if item.status == "FAIL")
    status = "PASS_WITH_DISCLOSED_LIMITATION" if fail_count == 0 else "FAIL"
    lines = [
        "# External Validity And Public Data Audit",
        "",
        "This read-only audit checks whether the manuscript and submission package keep the private-cohort, public-benchmark, and generalization boundaries explicit. It does not upgrade a private single-institution study into public-dataset validation.",
        "",
        "## Summary",
        "",
        f"- Status: {status}",
        f"- Checks evaluated: {len(rows)}",
        f"- Failing checks: {fail_count}",
        "- Public-generalization clearance: NOT CLAIMED",
        "- Fully automatic CT-to-CTV clearance: NOT CLAIMED",
        "- Final data-sharing policy confirmation: REQUIRED BEFORE SUBMISSION",
        "",
        "## Audit Checks",
        "",
        "| Check | Status | Evidence | Interpretation |",
        "| --- | --- | --- | --- |",
    ]
    for item in rows:
        lines.append(
            f"| {item.check} | {item.status} | {evidence_cell(item.evidence)} | {item.interpretation} |"
        )

    lines.extend(
        [
            "",
            "## Residual External-Validity Risks",
            "",
            "- The main cohort is a private institutional lung proton-therapy CT cohort.",
            "- No directly matched public sparse-prompt CTV completion benchmark is used.",
            "- The package supports reproducibility through aggregate metrics, scripts, tables, and figures, not through redistributable private imaging data.",
            "- Institutional data-sharing limits, IRB language, consent or waiver language, and final author approval must be confirmed before upload.",
            "",
            "## Interpretation",
            "",
            "- PASS_WITH_DISCLOSED_LIMITATION means the manuscript can defend its private-cohort evidence chain while openly retaining external-validity limitations.",
            "- It does not mean the method is validated for public-dataset generalization, external institutions, or fully automatic CT-to-CTV segmentation.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    fail_count = sum(1 for item in rows if item.status == "FAIL")
    status = "PASS_WITH_DISCLOSED_LIMITATION" if fail_count == 0 else "FAIL"
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"External validity status: {status}; failing checks: {fail_count}")


if __name__ == "__main__":
    main()
