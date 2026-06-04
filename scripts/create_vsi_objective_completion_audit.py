#!/usr/bin/env python3
"""Audit completion of the original VSI manuscript objective against evidence."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "objective_completion_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_objective_completion_audit_20260531.csv"


@dataclass(frozen=True)
class Evidence:
    rel: str
    line: int
    text: str


@dataclass(frozen=True)
class CompletionItem:
    requirement: str
    status: str
    evidence: list[Evidence]
    required_next_action: str
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


def contains_all(rel: str, needles: list[str]) -> bool:
    text = read_text(rel).lower()
    return all(needle.lower() in text for needle in needles)


def contains_any(rel: str, needles: list[str]) -> bool:
    text = read_text(rel).lower()
    return any(needle.lower() in text for needle in needles)


def find_hits(rel: str, needles: list[str]) -> list[Evidence]:
    lowered_needles = [needle.lower() for needle in needles]
    hits: list[Evidence] = []
    for idx, line in enumerate(read_lines(rel), 1):
        lowered_line = line.lower()
        if any(needle in lowered_line for needle in lowered_needles):
            hits.append(Evidence(rel, idx, " ".join(line.strip().split())))
    return hits


def first_hits(rel: str, needles: list[str], limit: int = 8) -> list[Evidence]:
    hits: list[Evidence] = []
    for needle in needles:
        found = find_hits(rel, [needle])
        if found:
            hits.append(found[0])
    return hits[:limit]


def evidence_cell(evidence: list[Evidence]) -> str:
    if not evidence:
        return "No current evidence found"
    cells = []
    for item in evidence[:8]:
        loc = item.rel if item.line == 0 else f"{item.rel}:{item.line}"
        text = item.text.replace("|", "\\|")
        if len(text) > 132:
            text = text[:129] + "..."
        cells.append(f"`{loc}` {text}")
    if len(evidence) > 8:
        cells.append(f"... plus {len(evidence) - 8} more")
    return "<br>".join(cells)


def status_for(ok: bool, blocker: bool = False, partial: bool = False) -> str:
    if blocker:
        return "BLOCKER"
    if partial:
        return "PARTIAL"
    return "PROVEN" if ok else "MISSING"


def build_items() -> list[CompletionItem]:
    items: list[CompletionItem] = []

    frontier_ok = contains_all(
        "frontier_recommendation_traceability.md",
        [
            "Status: PASS_WITH_CONTROLLED_FUTURE_WORK",
            "Missing recommendation links: 0",
            "Effective closed-loop idea",
        ],
    )
    items.append(
        CompletionItem(
            "Use the frontier literature/project report as the starting point.",
            status_for(frontier_ok),
            first_hits(
                "frontier_recommendation_traceability.md",
                [
                    "Status: PASS_WITH_CONTROLLED_FUTURE_WORK",
                    "Missing recommendation links: 0",
                    "Effective closed-loop idea",
                ],
            ),
            "Regenerate `frontier_recommendation_traceability.md` after any new experiment changes the paper story.",
            "The current package maps the frontier report to implemented evidence, controlled negative results, and future work.",
        )
    )

    experiments_ok = contains_all(
        "source_evidence_manifest.md",
        [
            "Paired Statistical Comparison",
            "Patient-Aggregated Paired Comparison",
            "Case-Level Robustness Analysis",
            "Patient-Aggregated Robustness Analysis",
            "Clinical Threshold",
            "Prompt-Efficiency Frontier",
            "Prompt-Placement Robustness",
            "OAR Constraint Sensitivity",
            "Doctor-Prior Graph Diagnostic",
            "Validation Split and Leakage Boundary Audit",
        ],
    )
    items.append(
        CompletionItem(
            "Conduct further experiments and summarize the effective evidence-backed idea.",
            status_for(experiments_ok),
            first_hits(
                "source_evidence_manifest.md",
                [
                    "Paired Statistical Comparison",
                    "Patient-Aggregated Paired Comparison",
                    "Case-Level Robustness Analysis",
                    "Patient-Aggregated Robustness Analysis",
                    "Clinical Threshold",
                    "Prompt-Efficiency Frontier",
                    "Prompt-Placement Robustness",
                    "OAR Constraint Sensitivity",
                    "Doctor-Prior Graph Diagnostic",
                    "Validation Split and Leakage Boundary Audit",
                ],
            )
            + first_hits("reports/vsi_paper_closure_status_20260531.md", ["Sparse-prompted multimodal CTV completion", "should not yet claim"]),
            "Keep doctor-prior graph refinement as future work unless a full grouped validation shows a deployable improvement.",
            "The evidence supports SDF core-envelope sparse-prompt completion, not a positive learned doctor-prior method.",
        )
    )

    main_claim_ok = contains_all(
        "main.tex",
        [
            "Sparse-Prompted Multimodal CTV Completion",
            "0.916",
            "0.871",
            "doctor-prior graph refinement as a closed-loop analysis",
        ],
    ) or contains_all(
        "main.tex",
        [
            "Sparse-Prompted Multimodal CTV Completion",
            "0.916",
            "0.871",
            "future refinement direction",
        ],
    )
    items.append(
        CompletionItem(
            "Form a closed-loop manuscript around an effective idea rather than an unsupported aspirational method.",
            status_for(main_claim_ok),
            first_hits("main.tex", ["Sparse-Prompted Multimodal CTV Completion", "0.916", "0.871", "future refinement direction"])
            + first_hits("peer_review_risk_audit.md", ["not a fully automatic CT-to-CTV segmentation paper", "Doctor-prior graph refinement is not yet a positive method"]),
            "Do not promote the diagnostic doctor-prior result until positive grouped validation exists.",
            "The manuscript states a defensible closed loop: SDF completion works, naive refinement fails, oracle headroom motivates future graph learning.",
        )
    )

    initial_draft_ok = contains_all(
        "initial_draft_delivery_handoff.md",
        [
            "Draft delivery status: INITIAL_DRAFT_DELIVERED",
            "current_experiment_paper_draft_20260601.md",
            "Human-Fill Items for Later Submission",
        ],
    ) and contains_all(
        "current_experiment_paper_draft_20260601.md",
        [
            "Draft status: initial manuscript draft based on current completed experiments",
            "Sparse-Prompted Multimodal CTV Completion with SDF Core-Envelope Priors",
        ],
    ) and contains_all(
        "final_submission_handoff.md",
        ["Initial draft delivery", "Initial-draft delivery is not a substitute for final journal submission readiness"],
    )
    items.append(
        CompletionItem(
            "Deliver the current-experiment initial draft while preserving later human-fill boundaries.",
            status_for(initial_draft_ok),
            first_hits("initial_draft_delivery_handoff.md", ["Draft delivery status:", "Markdown initial draft", "Human-Fill Items for Later Submission"])
            + first_hits("current_experiment_paper_draft_20260601.md", ["Draft status:", "Sparse-Prompted Multimodal CTV Completion with SDF Core-Envelope Priors"])
            + first_hits("final_submission_handoff.md", ["Initial draft delivery", "Initial-draft delivery is not a substitute"]),
            "Regenerate with `make -C manuscript_vsi_biomedical_data initial-draft` after any current-experiment draft edit.",
            "The requested initial draft is delivered and self-contained in the package; final submission metadata and signoffs remain separate blockers.",
        )
    )

    tex_project_ok = all(
        (PKG / rel).exists()
        for rel in [
            "main.tex",
            "references.bib",
            "highlights.tex",
            "cover_letter.txt",
            "submission_requirements_traceability.md",
            "reproducibility_manifest.md",
            "editorial_manager_upload_index.md",
            "Makefile",
        ]
    ) and contains_all("reports/vsi_archive_integrity_audit_20260531.md", ["Archive integrity status: PASS", "Missing expected files: 0"])
    items.append(
        CompletionItem(
            "Output a complete local TeX manuscript project and archive.",
            status_for(tex_project_ok),
            first_hits("reports/vsi_archive_integrity_audit_20260531.md", ["Archive integrity status: PASS", "Missing expected files: 0"])
            + first_hits("reproducibility_manifest.md", ["Manuscript Artifacts", "Regeneration Commands"]),
            "Keep regenerating the tarball after edits with `make -C manuscript_vsi_biomedical_data release`.",
            "The source package and dated archive are present and internally audited.",
        )
    )

    source_format_ok = contains_all(
        "tex_compile_readiness_audit.md",
        ["Source readiness status: SOURCE_CHECKS_PASS", "Source-level failure count: 0"],
    ) and contains_all(
        "source_layout_audit.md",
        ["Source-level status: ESTIMATE_IN_RANGE", "20-35 pages"],
    )
    rendered_pdf_format_ok = contains_all(
        "pdf_render_audit.md",
        ["PDF render audit status: READY_FOR_MANUAL_RENDERED_PDF_REVIEW", "Rendered page count:"],
    ) and contains_all(
        "rendered_pdf_visual_prescreen.md",
        [
            "Prescreen status: AUTOMATED_RENDERED_PDF_PRESCREEN_PASS_WITH_RESIDUAL_SIGNOFF_REQUIRED",
            "Rendered page count:",
            "Line-number visibility: PASS",
            "Page-number visibility: PASS",
            "Body layout: PASS",
            "Bibliography rendering: PASS",
        ],
    )
    format_requirements_ok = source_format_ok and rendered_pdf_format_ok
    items.append(
        CompletionItem(
            "Satisfy journal source-format requirements for the TeX project.",
            status_for(format_requirements_ok, partial=source_format_ok and not rendered_pdf_format_ok),
            first_hits("tex_compile_readiness_audit.md", ["Source readiness status: SOURCE_CHECKS_PASS", "Source-level failure count: 0", "Rendered PDF status"])
            + first_hits("source_layout_audit.md", ["Source-level status: ESTIMATE_IN_RANGE", "Estimated page count"])
            + first_hits("pdf_render_audit.md", ["PDF render audit status:", "Rendered page count:"])
            + first_hits("rendered_pdf_visual_prescreen.md", ["Prescreen status:", "Line-number visibility:", "Page-number visibility:", "Body layout:", "Bibliography rendering:"]),
            "Keep the rendered PDF prescreen current after any source, figure, bibliography, or metadata change; final submitting-author signoff is tracked separately.",
            "Source checks, page-count evidence, and automated rendered-PDF prescreen now support the source-format requirement; final human PDF signoff remains a separate blocker.",
        )
    )

    vsi_ok = contains_all(
        "submission_requirements_traceability.md",
        ["VSI: PR_Biomedical Data", "Special issue topic is multimodal biomedical pattern recognition"],
    ) and contains_all(
        "cover_letter.txt",
        [
            "VSI: PR_Biomedical Data",
            "state of the art",
            "public datasets",
            "validation",
            "not a patient-external validation",
            "not trained at cohort level",
        ],
    ) and contains_any(
        "cover_letter.txt",
        [
            "31 scan-level test scans from 21 unique patients",
            "31 independent test scans from 21 unique patients",
        ],
    )
    items.append(
        CompletionItem(
            "Meet the special issue topic, article-type, cover-letter, and validation-answer requirements.",
            status_for(vsi_ok),
            first_hits("submission_requirements_traceability.md", ["VSI: PR_Biomedical Data", "Special issue topic is multimodal biomedical pattern recognition"])
            + first_hits("cover_letter.txt", ["state of the art", "public datasets", "validation"])
            + first_hits("cover_letter.txt", ["31 scan-level test scans from 21 unique patients", "31 independent test scans from 21 unique patients", "not a patient-external validation", "not trained at cohort level"])
            + first_hits("official_requirements_snapshot.md", ["Snapshot status:", "Final official recheck before upload:", "Future upload recheck policy:"]),
            "Repeat the official-page recheck if upload occurs after the recorded access date or if either official page changes.",
            "The local package records the article type, required cover-letter answers, dated official-page recheck, and scan-level/non-patient-external validation boundary.",
        )
    )

    official_recheck_ready = not contains_any(
        "official_requirements_snapshot.md",
        ["Final official recheck before upload: REQUIRED", "OFFICIAL_REQUIREMENTS_RECHECK_REQUIRED"],
    )
    items.append(
        CompletionItem(
            "Recheck official special-issue and guide requirements before real upload.",
            status_for(official_recheck_ready, partial=not official_recheck_ready),
            first_hits(
                "official_requirements_snapshot.md",
                [
                    "Snapshot status:",
                    "Official source URLs:",
                    "Access date:",
                    "Final official recheck before upload:",
                    "Future upload recheck policy:",
                ],
            )
            + first_hits("submission_blocker_audit.md", ["WARNING_OFFICIAL_REQUIREMENTS_RECHECK"])
            + first_hits("final_submission_handoff.md", ["Official special-issue and guide recheck"]),
            "Repeat the official-page recheck if upload occurs after the recorded access date or if either official page changes.",
            "The local snapshot captures a current dated recheck; future upload timing still controls whether it must be repeated.",
        )
    )

    evidence_ok = contains_all(
        "external_validity_public_data_audit.md",
        ["PASS_WITH_DISCLOSED_LIMITATION", "Public benchmark limitation disclosed"],
    ) and contains_all(
        "source_evidence_manifest.md",
        ["Public-dataset generalization", "Full-scale learned doctor-prior graph improvement"],
    ) and contains_all(
        "validation_split_leakage_audit.md",
        ["PASS_WITH_SCAN_LEVEL_LIMITATION", "31 scans from 21 unique patients", "must not claim patient-external validation"],
    )
    items.append(
        CompletionItem(
            "Control unsupported claims and data-sharing limitations.",
            status_for(evidence_ok),
            first_hits("external_validity_public_data_audit.md", ["PASS_WITH_DISCLOSED_LIMITATION", "Public benchmark limitation disclosed"])
            + first_hits("validation_split_leakage_audit.md", ["PASS_WITH_SCAN_LEVEL_LIMITATION", "31 scans from 21 unique patients", "must not claim patient-external validation"])
            + first_hits("source_evidence_manifest.md", ["Public-dataset generalization", "Full-scale learned doctor-prior graph improvement"]),
            "Confirm final institutional data-sharing limits and ethics language before upload.",
            "The package avoids public-generalization, patient-external validation, and fully automatic CT-to-CTV claims.",
        )
    )

    metadata_ready = contains_all("submission_metadata_lock_audit.md", ["Status: READY_FOR_METADATA_LOCK"])
    author_declaration_ready = contains_all(
        "author_declaration_signoff_form.md",
        ["Signoff status: AUTHOR_DECLARATION_SIGNOFF_COMPLETE", "Blocking signoff rows: 0"],
    )
    items.append(
        CompletionItem(
            "Finalize author, affiliation, corresponding-author, ethics, funding, CRediT metadata, and author declarations.",
            status_for(False, blocker=not (metadata_ready and author_declaration_ready)),
            first_hits(
                "submission_metadata_lock_audit.md",
                [
                    "Status: NOT_READY_FOR_METADATA_LOCK",
                    "Metadata field blockers:",
                    "main.tex placeholder hit count:",
                    "cover_letter.txt placeholder hit count:",
                ],
            )
            + first_hits("submission_blocker_audit.md", ["BLOCKER_AUTHOR_METADATA", "BLOCKER_ETHICS_CONSENT", "BLOCKER_FUNDING_ACKNOWLEDGEMENTS", "BLOCKER_CREDIT_AUTHORSHIP"])
            + first_hits("metadata_application_plan.md", ["Status: BLOCKED_BY_PLACEHOLDERS", "Apply command after final author approval", "Targets:"])
            + first_hits("submission_metadata_completion_packet.md", ["Packet status: BLOCKED_BY_REQUIRED_METADATA", "Required metadata blockers:", "Human fill form:", "Field Ownership"])
            + first_hits("submission_metadata_author_fill_form.md", ["Required fields still blocked:", "Approved final value:", "After Filling"])
            + first_hits("submission_metadata_fill_form_sync.md", ["Sync status:", "Blocking rows:", "Author-approved YAML sync command:"])
            + first_hits("author_declaration_signoff_form.md", ["Signoff status:", "Declaration signoff checklist rows:", "Blocking signoff rows:", "Source metadata form:"])
            + first_hits("final_submission_handoff.md", ["Author, ethics, funding, and CRediT metadata", "Author-approved metadata application", "Author declarations and final approval"]),
            "Use `submission_metadata_author_fill_form.md` to collect approved values, run `make -C manuscript_vsi_biomedical_data metadata-fill-sync`, apply the YAML sync after final approval, run `python scripts/apply_vsi_submission_metadata.py --apply`, record approvals in `author_declaration_signoff_form.md`, and rerun release.",
            "Human-supplied institutional metadata and final author/declaration approvals are still missing, but the package now includes a fill form, a YAML sync gate, a declaration signoff form, and a validation path for completing them.",
        )
    )

    pdf_artifact_ready = contains_all(
        "pdf_render_audit.md",
        ["PDF render audit status: READY_FOR_MANUAL_RENDERED_PDF_REVIEW", "Rendered page count:"],
    )
    pdf_signoff_ready = contains_all(
        "rendered_pdf_author_signoff_form.md",
        ["Signoff status: RENDERED_PDF_AUTHOR_SIGNOFF_COMPLETE", "Blocking signoff rows: 0"],
    )
    items.append(
        CompletionItem(
            "Compile and inspect the final PDF.",
            status_for(pdf_artifact_ready and pdf_signoff_ready, blocker=(not pdf_artifact_ready) or not pdf_signoff_ready),
            first_hits("reports/vsi_manuscript_package_verification.md", ["accepted TeX backend", "tool available via accepted fallback"])
            + first_hits("tex_compile_readiness_audit.md", ["Rendered PDF status: NOT VERIFIED", "Final compile command"])
            + first_hits("pdf_compilation_handoff.md", ["PDF handoff status:", "Compile command in a TeX-enabled environment", "Rendered page-count inspection"])
            + first_hits("pdf_render_audit.md", ["PDF render audit status:", "Accepted TeX backend:", "Rendered page count:", "Manual rendered review status:"])
            + first_hits("rendered_pdf_visual_prescreen.md", ["Prescreen status:", "Rendered page count:", "Final submitting-author rendered-PDF signoff: STILL REQUIRED"])
            + first_hits("rendered_pdf_author_signoff_form.md", ["Signoff status:", "PDF signoff checklist rows:", "Blocking signoff rows:"])
            + first_hits("final_submission_handoff.md", ["Rendered PDF compile and inspection", "Final PDF command in a TeX-enabled environment"]),
            "Inspect the compiled PDF manually for page count, line numbers, tables, figures, captions, bibliography, and clinical overlays; record decisions in `rendered_pdf_author_signoff_form.md`; rerun `make -C manuscript_vsi_biomedical_data pdf-render-compile` after any source change.",
            "The environment/artifact portion of PDF compilation and an automated rendered-PDF visual/text prescreen are now recorded, but final submitting-author signoff remains incomplete until the rendered-PDF signoff form is approved row by row.",
        )
    )

    reference_ready = not contains_any("citation_metadata_audit.md", ["Remaining Manual Citation Tasks"])
    items.append(
        CompletionItem(
            "Complete manual publisher-record reference verification.",
            status_for(False, partial=not reference_ready),
            first_hits("citation_metadata_audit.md", ["Structural failures: 0", "Remaining Manual Citation Tasks"])
            + first_hits("reference_identifier_audit.md", ["Identifier failures: 0"])
            + first_hits(
                "reference_online_metadata_audit.md",
                ["Online metadata audit status:", "Metadata fetch failures: 0", "Hard review rows: 0", "Title review rows: 0"],
            )
            + first_hits(
                "reference_publisher_verification_packet.md",
                ["Packet status: MANUAL_PUBLISHER_REVIEW_REQUIRED", "Entries queued:", "arXiv-only entries:"],
            )
            + first_hits("reference_publisher_signoff_form.md", ["Signoff status:", "Entries requiring signoff:", "Blocking signoff rows:"])
            + first_hits("final_submission_handoff.md", ["Publisher-record reference review"]),
            "Use `reference_online_metadata_audit.md` as the online metadata precheck, `reference_publisher_verification_packet.md` as the review queue, and `reference_publisher_signoff_form.md` to record final manual verification against publisher, DOI, PubMed, arXiv, proceedings, or open-access records.",
            "Local structural checks, identifier syntax checks, and online title/identifier metadata checks pass without hard failures, but final publisher-record signoff remains.",
        )
    )

    overlay_ready = contains_all("clinical_overlay_signoff_form.md", ["Signoff status: CLINICAL_OVERLAY_SIGNOFF_COMPLETE", "Blocking signoff rows: 0"])
    items.append(
        CompletionItem(
            "Complete clinical overlay pixel PHI review.",
            status_for(overlay_ready, partial=not overlay_ready),
            first_hits("figure_privacy_integrity_audit.md", ["Clinical image panels requiring final visual review:", "Filename PHI hits: 0", "Metadata PHI hits: 0"])
            + first_hits(
                "clinical_overlay_visual_review_packet.md",
                ["Packet status: CLINICAL_OVERLAY_VISUAL_REVIEW_REQUIRED", "Clinical overlay files queued:", "Clinical-owner signoff status:"],
            )
            + first_hits(
                "clinical_overlay_ai_visual_prescreen.md",
                ["AI visual prescreen status:", "Visible PHI-like text after AI prescreen:", "Case/date title tokens after anonymization:"],
            )
            + first_hits(
                "clinical_overlay_signoff_form.md",
                ["Signoff status:", "Clinical overlay files requiring signoff:", "Blocking signoff rows:"],
            )
            + first_hits("final_submission_handoff.md", ["Clinical figure visual PHI review"]),
            "Use `clinical_overlay_visual_review_packet.md` and `clinical_overlay_ai_visual_prescreen.md` to inspect all queued clinical overlay PNGs at full resolution and again in the rendered PDF, then record final decisions in `clinical_overlay_signoff_form.md`.",
            "Metadata-level checks pass and an AI visual prescreen records no visible case/date title tokens after regeneration, but clinical-owner pixel review remains incomplete until the signoff form is approved row by row.",
        )
    )

    upload_ready = contains_all("reports/vsi_manuscript_package_verification.md", ["Status: **READY**"])
    items.append(
        CompletionItem(
            "Declare the full original objective complete.",
            status_for(False, blocker=not upload_ready),
            first_hits("reports/vsi_manuscript_package_verification.md", ["Status: **NOT READY**"])
            + first_hits("submission_blocker_audit.md", ["Outstanding blocker count:"])
            + first_hits("final_submission_handoff.md", ["Handoff decision: NOT_READY_FOR_UPLOAD", "Final release archive"]),
            "Resolve all blocker rows, compile/inspect the PDF, rerun release, then rerun this audit.",
            "The objective is not complete while real-submission blockers and PDF verification remain unresolved.",
        )
    )

    return items


def write_csv(items: list[CompletionItem]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["requirement", "status", "evidence", "required_next_action", "interpretation"],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "requirement": item.requirement,
                    "status": item.status,
                    "evidence": " | ".join(
                        f"{e.rel}:{e.line}:{e.text}" if e.line else f"{e.rel}:{e.text}" for e in item.evidence
                    ),
                    "required_next_action": item.required_next_action,
                    "interpretation": item.interpretation,
                }
            )


def write_markdown(items: list[CompletionItem]) -> None:
    blocker_count = sum(1 for item in items if item.status == "BLOCKER")
    partial_count = sum(1 for item in items if item.status == "PARTIAL")
    missing_count = sum(1 for item in items if item.status == "MISSING")
    proven_count = sum(1 for item in items if item.status == "PROVEN")
    decision = "COMPLETE" if not blocker_count and not partial_count and not missing_count else "NOT_COMPLETE"

    lines = [
        "# Original Objective Completion Audit",
        "",
        "This audit evaluates the original user objective against current repository evidence. It is deliberately stricter than the source verifier: source-structure success is not treated as proof of real submission readiness.",
        "",
        "## Summary",
        "",
        f"- Completion decision: {decision}",
        f"- Requirements audited: {len(items)}",
        f"- Proven requirements: {proven_count}",
        f"- Partial requirements: {partial_count}",
        f"- Missing requirements: {missing_count}",
        f"- Blocking requirements: {blocker_count}",
        "- Goal status recommendation: keep active until all BLOCKER and PARTIAL rows are resolved."
        if decision != "COMPLETE"
        else "- Goal status recommendation: eligible for completion after final human submission approval is confirmed.",
        "",
        "## Requirement Audit",
        "",
        "| Requirement | Status | Evidence | Required next action | Interpretation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in items:
        lines.append(
            f"| {item.requirement} | {item.status} | {evidence_cell(item.evidence)} | {item.required_next_action} | {item.interpretation} |"
        )

    lines.extend(
        [
            "",
            "## Completion Rule",
            "",
            "- Mark the active goal complete only when this audit reports `Completion decision: COMPLETE`, the manuscript verifier reports `Status: **READY**`, the metadata lock audit reports `READY_FOR_METADATA_LOCK`, and the rendered PDF has been compiled and inspected.",
            "- Do not treat archive integrity, source compile-readiness, or absence of source failures as substitutes for final author metadata, ethics/funding language, author approval, or rendered PDF inspection.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    items = build_items()
    write_csv(items)
    write_markdown(items)
    blocker_count = sum(1 for item in items if item.status == "BLOCKER")
    partial_count = sum(1 for item in items if item.status == "PARTIAL")
    missing_count = sum(1 for item in items if item.status == "MISSING")
    decision = "COMPLETE" if not blocker_count and not partial_count and not missing_count else "NOT_COMPLETE"
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(
        f"Objective completion decision: {decision}; blockers={blocker_count}; partial={partial_count}; missing={missing_count}"
    )


if __name__ == "__main__":
    main()
