#!/usr/bin/env python3
"""Trace the frontier-report recommendations to the current VSI manuscript."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
REPORT = ROOT / "reports" / "frontier_literature_and_project_idea_20260531.md"
MD_OUT = PKG / "frontier_recommendation_traceability.md"
CSV_OUT = ROOT / "reports" / "vsi_frontier_recommendation_traceability_20260531.csv"


@dataclass(frozen=True)
class Evidence:
    rel: str
    line: int
    text: str


@dataclass(frozen=True)
class TraceRow:
    recommendation: str
    implementation_status: str
    frontier_evidence: list[Evidence]
    manuscript_evidence: list[Evidence]
    interpretation: str


def path_for(rel: str) -> Path:
    if rel.startswith("reports/") or rel.startswith("results/") or rel.startswith("scripts/"):
        return ROOT / rel
    return PKG / rel


def read_lines(rel: str) -> list[str]:
    path = path_for(rel)
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


def first_hits(rel: str, needles: list[str], limit: int = 6) -> list[Evidence]:
    hits: list[Evidence] = []
    for needle in needles:
        found = find_hits(rel, [needle])
        if found:
            hits.append(found[0])
    return hits[:limit]


def contains_all(rel: str, needles: list[str]) -> bool:
    text = read_text(rel).lower()
    return all(needle.lower() in text for needle in needles)


def evidence_cell(evidence: list[Evidence]) -> str:
    if not evidence:
        return "No local evidence found"
    cells = []
    for item in evidence[:6]:
        loc = item.rel if item.line == 0 else f"{item.rel}:{item.line}"
        text = item.text.replace("|", "\\|")
        if len(text) > 128:
            text = text[:125] + "..."
        cells.append(f"`{loc}` {text}")
    if len(evidence) > 6:
        cells.append(f"... plus {len(evidence) - 6} more")
    return "<br>".join(cells)


def status_ok(status: str) -> bool:
    return status in {"IMPLEMENTED", "VALIDATED", "CONTROLLED_NEGATIVE", "DISCLOSED_LIMITATION"}


def build_rows() -> list[TraceRow]:
    rows: list[TraceRow] = []

    rows.append(
        TraceRow(
            "Reframe the project from fully automatic CT-to-CTV segmentation to sparse-prompted CTV completion.",
            "IMPLEMENTED"
            if contains_all("main.tex", ["sparse-prompted CTV completion", "fully automatic CT-to-mask segmentation"])
            and contains_all("peer_review_risk_audit.md", ["not a fully automatic CT-to-CTV segmentation paper"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["CT + OAR", "sparse prompt", "fully automatic"]),
            first_hits("main.tex", ["sparse-prompted CTV completion", "fully automatic CT-to-mask segmentation"])
            + first_hits("peer_review_risk_audit.md", ["not a fully automatic CT-to-CTV segmentation paper"]),
            "The manuscript adopts the frontier report's task reframing and treats fully automatic methods as baselines.",
        )
    )

    rows.append(
        TraceRow(
            "Use SDF propagation and a core-envelope representation as the central closed-loop method.",
            "VALIDATED"
            if contains_all("main.tex", ["SDF propagation", "core-envelope"])
            and contains_all("source_evidence_manifest.md", ["Proposed SDF sparse-prompt K=7 Dice", "Core-Envelope Ablation"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["SDF propagation", "core-envelope", "K=7 SDF pseudo label"]),
            first_hits("main.tex", ["SDF propagation", "core-envelope", "proposed SDF pseudo-label"])
            + first_hits("source_evidence_manifest.md", ["Proposed SDF sparse-prompt K=7 Dice", "Core-Envelope Ablation"]),
            "The validated paper contribution is SDF sparse-prompt completion plus core-envelope analysis.",
        )
    )

    rows.append(
        TraceRow(
            "Benchmark against fully automatic networks and promptable segmentation baselines.",
            "VALIDATED"
            if contains_all("main.tex", ["nnU-Net", "DiffUNet", "SAM-Med3D"])
            and contains_all("source_evidence_manifest.md", ["nnU-Net fully automatic", "SAM-Med3D sparse K=7"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["SAM-Med3D", "fully automatic", "promptable segmentation"]),
            first_hits("main.tex", ["nnU-Net", "DiffUNet", "SAM-Med3D"])
            + first_hits("source_evidence_manifest.md", ["nnU-Net fully automatic", "SAM-Med3D sparse K=7"]),
            "The main table and paired tests compare the SDF completion against deployable automatic and promptable baselines.",
        )
    )

    rows.append(
        TraceRow(
            "Run prompt-count, prompt-efficiency, and prompt-placement studies instead of relying on one prompt setting.",
            "VALIDATED"
            if contains_all("source_evidence_manifest.md", ["Prompt-Count Sensitivity", "Prompt-Efficiency Frontier", "Prompt-Placement Robustness"])
            and contains_all("main.tex", ["K=3", "K=5", "K=7", "prompt-efficiency frontier", "Prompt-placement robustness"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["K = 3, 5, 7", "strategies = even_nonempty", "PAM"]),
            first_hits("main.tex", ["K=3", "K=5", "K=7", "prompt-efficiency frontier", "Prompt-placement robustness"])
            + first_hits("source_evidence_manifest.md", ["Prompt-Count Sensitivity", "Prompt-Efficiency Frontier", "Prompt-Placement Robustness"]),
            "The manuscript quantifies prompt-count sensitivity, marginal prompt efficiency, and three prompt-placement strategies.",
        )
    )

    rows.append(
        TraceRow(
            "Use oracle envelope headroom to prove the uncertain region is worth studying.",
            "VALIDATED"
            if contains_all("main.tex", ["oracle envelope", "headroom"])
            and contains_all("source_evidence_manifest.md", ["Oracle Headroom", "Oracle rows are not deployable"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["oracle headroom", "expanded envelope", "envelope"]),
            first_hits("main.tex", ["oracle envelope", "headroom", "not a deployable result"])
            + first_hits("source_evidence_manifest.md", ["Oracle Headroom", "Oracle rows are not deployable"]),
            "Oracle rows are used as upper bounds that justify future refinement without inflating deployable claims.",
        )
    )

    rows.append(
        TraceRow(
            "Test simple HU/support/OAR refinement and do not hide negative results.",
            "CONTROLLED_NEGATIVE"
            if contains_all("main.tex", ["Simple support, HU", "does not improve"])
            and contains_all("source_evidence_manifest.md", ["Simple HU/support refinement does not improve"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["HU/support/core-distance", "core-only", "refinement"]),
            first_hits("main.tex", ["Simple support, HU", "does not improve"])
            + first_hits("source_evidence_manifest.md", ["Simple HU/support refinement does not improve"]),
            "The negative refinement result is retained and used to sharpen the final idea.",
        )
    )

    rows.append(
        TraceRow(
            "Treat OAR anatomy as a constraint/audit channel and test hard-constraint sensitivity.",
            "VALIDATED"
            if contains_all("main.tex", ["OAR hard-constraint sensitivity", "not presented as the primary source"])
            and contains_all("source_evidence_manifest.md", ["OAR Constraint Sensitivity"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["OAR", "hard exclusion", "anatomy/OAR"]),
            first_hits("main.tex", ["OAR hard-constraint sensitivity", "not presented as the primary source"])
            + first_hits("source_evidence_manifest.md", ["OAR Constraint Sensitivity"]),
            "OAR context remains part of the multimodal formulation, while the evidence avoids overclaiming it as the Dice driver.",
        )
    )

    rows.append(
        TraceRow(
            "Evaluate the doctor-prior graph idea but downgrade it if current evidence is not positive.",
            "CONTROLLED_NEGATIVE"
            if contains_all("main.tex", ["doctor-prior diagnostic", "did not beat"])
            and contains_all("peer_review_risk_audit.md", ["Doctor-prior graph refinement is not yet a positive method"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["Doctor-Prior Guided Graph Refinement", "cluster inclusion classifier", "graph cut / random walker"]),
            first_hits("main.tex", ["doctor-prior diagnostic", "did not beat", "future refinement direction"])
            + first_hits("peer_review_risk_audit.md", ["Doctor-prior graph refinement is not yet a positive method"]),
            "The current paper closes the loop by reporting a diagnostic failure and preserving graph learning as future work.",
        )
    )

    rows.append(
        TraceRow(
            "Report paired statistics, robustness distributions, and review gates for the independent test set.",
            "VALIDATED"
            if contains_all("source_evidence_manifest.md", ["Paired Statistical Comparison", "Case-Level Robustness Analysis", "Clinical Threshold"])
            and contains_all("main.tex", ["paired Wilcoxon", "Holm-corrected", "clinical-threshold audit"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["Delta Dice", "improved-case ratio", "Dice/HD95/ASD"]),
            first_hits("main.tex", ["paired Wilcoxon", "Holm-corrected", "clinical-threshold audit"])
            + first_hits("source_evidence_manifest.md", ["Paired Statistical Comparison", "Case-Level Robustness Analysis", "Clinical Threshold"]),
            "The validation package now includes paired tests, robustness summaries, and fixed review-gate counts.",
        )
    )

    rows.append(
        TraceRow(
            "Keep the private-cohort/public-benchmark limitation explicit.",
            "DISCLOSED_LIMITATION"
            if contains_all("external_validity_public_data_audit.md", ["PASS_WITH_DISCLOSED_LIMITATION", "Public benchmark limitation disclosed"])
            and contains_all("data_availability_statement.txt", ["private institutional", "cannot be publicly released"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["65", "BBDM", "public"]),
            first_hits("external_validity_public_data_audit.md", ["PASS_WITH_DISCLOSED_LIMITATION", "Public benchmark limitation disclosed"])
            + first_hits("data_availability_statement.txt", ["private institutional", "cannot be publicly released"]),
            "The paper does not claim public-dataset generalization and keeps data-sharing limits explicit.",
        )
    )

    rows.append(
        TraceRow(
            "Translate the frontier idea into a Pattern Recognition VSI manuscript package.",
            "IMPLEMENTED"
            if contains_all("submission_requirements_traceability.md", ["VSI: PR_Biomedical Data", "Reproducibility manifest included"])
            and contains_all("reproducibility_manifest.md", ["Regeneration Commands", "Manuscript Artifacts"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["weakly supervised medical image segmentation", "data preprocessing", "Idea"]),
            first_hits("submission_requirements_traceability.md", ["VSI: PR_Biomedical Data", "Reproducibility manifest included"])
            + first_hits("reproducibility_manifest.md", ["Regeneration Commands", "Manuscript Artifacts"]),
            "The current deliverable is a complete local TeX source package plus reproducibility and submission audits.",
        )
    )

    rows.append(
        TraceRow(
            "Define the effective closed-loop paper idea from the evidence rather than from the aspirational method name alone.",
            "IMPLEMENTED"
            if contains_all("reports/vsi_paper_closure_status_20260531.md", ["Sparse-prompted multimodal CTV completion", "should not yet claim"])
            and contains_all("main.tex", ["validated contribution", "future refinement direction"])
            else "MISSING",
            first_hits("reports/frontier_literature_and_project_idea_20260531.md", ["Idea", "Doctor-Prior", "BBDM"]),
            first_hits("reports/vsi_paper_closure_status_20260531.md", ["Sparse-prompted multimodal CTV completion", "should not yet claim"])
            + first_hits("main.tex", ["validated contribution", "future refinement direction"]),
            "The final paper idea is SDF core-envelope sparse-prompt completion, with doctor-prior graph refinement as a justified future direction.",
        )
    )

    return rows


def write_csv(rows: list[TraceRow]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "recommendation",
                "implementation_status",
                "frontier_evidence",
                "manuscript_evidence",
                "interpretation",
            ],
        )
        writer.writeheader()
        for item in rows:
            writer.writerow(
                {
                    "recommendation": item.recommendation,
                    "implementation_status": item.implementation_status,
                    "frontier_evidence": " | ".join(
                        f"{e.rel}:{e.line}:{e.text}" if e.line else f"{e.rel}:{e.text}" for e in item.frontier_evidence
                    ),
                    "manuscript_evidence": " | ".join(
                        f"{e.rel}:{e.line}:{e.text}" if e.line else f"{e.rel}:{e.text}" for e in item.manuscript_evidence
                    ),
                    "interpretation": item.interpretation,
                }
            )


def write_markdown(rows: list[TraceRow]) -> None:
    missing_count = sum(1 for item in rows if not status_ok(item.implementation_status))
    controlled_negative_count = sum(1 for item in rows if item.implementation_status == "CONTROLLED_NEGATIVE")
    limitation_count = sum(1 for item in rows if item.implementation_status == "DISCLOSED_LIMITATION")
    status = "PASS_WITH_CONTROLLED_FUTURE_WORK" if missing_count == 0 else "FAIL"

    lines = [
        "# Frontier Recommendation Traceability",
        "",
        "This audit maps `reports/frontier_literature_and_project_idea_20260531.md` to the current manuscript package. It distinguishes validated implementation from controlled negative evidence and disclosed limitations.",
        "",
        "## Summary",
        "",
        f"- Status: {status}",
        f"- Recommendations audited: {len(rows)}",
        f"- Missing recommendation links: {missing_count}",
        f"- Controlled negative findings retained: {controlled_negative_count}",
        f"- Disclosed limitations retained: {limitation_count}",
        "- Effective closed-loop idea: sparse-prompted SDF core-envelope CTV completion; doctor-prior graph refinement remains future work.",
        "",
        "## Traceability Table",
        "",
        "| Frontier recommendation | Implementation status | Frontier report evidence | Manuscript/package evidence | Interpretation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        lines.append(
            f"| {item.recommendation} | {item.implementation_status} | {evidence_cell(item.frontier_evidence)} | {evidence_cell(item.manuscript_evidence)} | {item.interpretation} |"
        )

    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "- The aspirational frontier idea was doctor-prior guided graph refinement.",
            "- The current validated manuscript idea is narrower and better supported: sparse-prompted SDF core-envelope CTV completion.",
            "- The diagnostic doctor-prior result is retained because it explains why the next refinement step should be cluster-level, calibrated, and group-validated before being promoted.",
            "- This audit should be regenerated after any new experiment changes the main claim.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    if not REPORT.exists():
        raise SystemExit(f"Missing frontier report: {REPORT}")
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    missing_count = sum(1 for item in rows if not status_ok(item.implementation_status))
    status = "PASS_WITH_CONTROLLED_FUTURE_WORK" if missing_count == 0 else "FAIL"
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Frontier traceability status: {status}; missing recommendation links: {missing_count}")


if __name__ == "__main__":
    main()
