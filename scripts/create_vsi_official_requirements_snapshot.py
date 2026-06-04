#!/usr/bin/env python3
"""Create a dated snapshot of official VSI and Pattern Recognition requirements."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "official_requirements_snapshot.md"
CSV_OUT = ROOT / "reports" / "vsi_official_requirements_snapshot_20260531.csv"

SPECIAL_ISSUE_URL = "https://www.sciencedirect.com/special-issue/329765/multimodal-pattern-recognition-for-biomedical-data-theories-algorithms-and-applications"
GUIDE_URL = "https://www.sciencedirect.com/journal/pattern-recognition/publish/guide-for-authors"
ACCESS_DATE = "2026-06-01 Asia/Shanghai"
SNAPSHOT_STATUS = "OFFICIAL_REQUIREMENTS_RECHECKED_2026_06_01"
FINAL_RECHECK_STATUS = "COMPLETED_ON_2026_06_01"
FUTURE_RECHECK_POLICY = "Repeat the official-page recheck if upload occurs after 2026-06-01 or if either official page changes before upload."


@dataclass(frozen=True)
class Requirement:
    item_id: str
    source: str
    section: str
    requirement: str
    local_evidence: str
    status: str
    remaining_action: str


REQUIREMENTS = [
    Requirement(
        "SPECIAL_ISSUE_SCOPE",
        SPECIAL_ISSUE_URL,
        "Call for papers / keywords",
        "The article must fit multimodal biomedical pattern recognition, medical data processing, AI methods, and clinical/biomedical applications.",
        "main.tex; cover_letter.txt; submission_requirements_traceability.md",
        "PASS",
        "Keep the task framed as CT, OAR anatomy, SDF spatial priors, and sparse clinician prompts, not as generic fully automatic CTV segmentation.",
    ),
    Requirement(
        "SPECIAL_ISSUE_WINDOW",
        SPECIAL_ISSUE_URL,
        "Manuscript submission information",
        "The special issue submission window is 2026-02-01 to 2026-08-31, with deadline 2026-08-31.",
        "submission_metadata_template.yaml; editorial_manager_upload_index.md",
        "PASS",
        FUTURE_RECHECK_POLICY,
    ),
    Requirement(
        "ARTICLE_TYPE",
        SPECIAL_ISSUE_URL,
        "Manuscript submission information",
        "The online submission article type must be VSI: PR_Biomedical Data.",
        "submission_metadata_template.yaml; cover_letter.txt; editorial_manager_upload_index.md",
        "PASS",
        "Submitting author must select the article type in Editorial Manager.",
    ),
    Requirement(
        "PEER_REVIEW_CRITERIA",
        SPECIAL_ISSUE_URL,
        "Manuscript submission information",
        "Submissions are evaluated for originality, significance, technical quality, and clarity.",
        "main.tex; peer_review_risk_audit.md; source_evidence_manifest.md",
        "WARNING",
        "Peer review determines final suitability; keep claim boundaries and negative results explicit.",
    ),
    Requirement(
        "EDITABLE_SOURCE",
        GUIDE_URL,
        "Writing and formatting / File format",
        "Editable source files are required for text, figures, tables, and text graphics; PDF is not an acceptable source file.",
        "main.tex; references.bib; tables/*.tex; figures/*.png; Makefile",
        "PASS",
        "Upload editable source and support files; final PDF is still required for visual inspection but not as the only source.",
    ),
    Requirement(
        "LATEX_TEMPLATE",
        GUIDE_URL,
        "Writing and formatting / LaTeX",
        "Elsevier encourages use of its LaTeX template and requires relevant editable source files for LaTeX submissions.",
        "cas-sc.cls; cas-common.sty; cas-model2-names.bst; main.tex",
        "PASS",
        "Compile in a TeX-enabled environment and inspect rendered output.",
    ),
    Requirement(
        "PAGE_LAYOUT",
        GUIDE_URL,
        "Journal specific information / Page limit",
        "Regular articles should be single-column, double-spaced, numbered, and approximately 20-35 pages.",
        "main.tex; source_layout_audit.md; tex_compile_readiness_audit.md; pdf_render_audit.md; rendered_pdf_visual_prescreen.md",
        "PASS",
        "Rendered page count and sampled layout pass; final submitting-author PDF signoff remains required after metadata edits.",
    ),
    Requirement(
        "TITLE_PAGE",
        GUIDE_URL,
        "Title page",
        "Title page must include concise title, author names, affiliations, and corresponding-author contact details.",
        "main.tex; submission_metadata_completion_packet.md; author_submission_info_needed.md",
        "BLOCKER",
        "Final author list, affiliations, corresponding author email/address, and author order must be supplied by the PI/corresponding author.",
    ),
    Requirement(
        "ABSTRACT",
        GUIDE_URL,
        "Abstract",
        "Abstract must be concise, factual, standalone, and no more than 250 words.",
        "main.tex; reports/vsi_manuscript_package_verification.md",
        "PASS",
        "Recheck after any manuscript edits.",
    ),
    Requirement(
        "KEYWORDS",
        GUIDE_URL,
        "Keywords",
        "The manuscript must provide 1-7 English keywords for indexing.",
        "main.tex; reports/vsi_manuscript_package_verification.md",
        "PASS",
        "Recheck after any keyword edits.",
    ),
    Requirement(
        "HIGHLIGHTS",
        GUIDE_URL,
        "Highlights",
        "Highlights are mandatory, must be in a separate editable file, and should contain 3-5 bullets of no more than 85 characters each.",
        "highlights.tex; reports/vsi_manuscript_package_verification.md",
        "PASS",
        "Upload highlights as a separate editable file.",
    ),
    Requirement(
        "GRAPHICAL_ABSTRACT",
        GUIDE_URL,
        "Graphical abstract",
        "A graphical abstract is encouraged and should be a separate readable file at least 531 x 1328 pixels if provided.",
        "figures/graphical_abstract.png; graphical_abstract_description.txt; reports/vsi_manuscript_package_verification.md",
        "PASS",
        "Final author may choose whether to upload the optional graphical abstract after design review.",
    ),
    Requirement(
        "TABLES",
        GUIDE_URL,
        "Tables",
        "Tables must be editable text, cited in the manuscript, captioned, consecutively numbered, and should avoid vertical rules and shading.",
        "tables/*.tex; main.tex; tex_compile_readiness_audit.md",
        "PASS",
        "Inspect rendered tables after PDF compilation.",
    ),
    Requirement(
        "FIGURES",
        GUIDE_URL,
        "Figures, images and artwork",
        "Figures must be cited, numbered in order, provided as separate files, captioned, and meet resolution/readability expectations.",
        "figures/*.png; figure_privacy_integrity_audit.md; clinical_overlay_visual_review_packet.md; clinical_overlay_ai_visual_prescreen.md",
        "WARNING",
        "Source resolution checks pass, but rendered-PDF inspection and clinical overlay pixel signoff remain required.",
    ),
    Requirement(
        "GENAI_ARTWORK_POLICY",
        GUIDE_URL,
        "Generative AI and figures/images/artwork",
        "Generative AI or AI-assisted tools must not be used to create or alter submitted artwork unless the use is part of the research method and described reproducibly.",
        "scripts/create_vsi_manuscript_figures.py; generative_ai_statement.txt; graphical_abstract_description.txt",
        "PASS",
        "Keep submitted artwork generated from project data/workflow scripts and do not replace it with AI-generated artwork without editor/publisher clearance.",
    ),
    Requirement(
        "RESEARCH_DATA_STATEMENT",
        GUIDE_URL,
        "Research data / Data statement",
        "Authors must state data availability at submission; if data cannot be shared, the reason must be stated.",
        "data_availability_statement.txt; external_validity_public_data_audit.md; author_declaration_signoff_form.md",
        "WARNING",
        "Institutional data-sharing limits and ethics language must be confirmed and signed off before upload.",
    ),
    Requirement(
        "REFERENCES",
        GUIDE_URL,
        "References",
        "All cited references must appear in the reference list and vice versa; Pattern Recognition requests 35-55 relevant references and encourages DOI correctness.",
        "references.bib; citation_metadata_audit.md; reference_identifier_audit.md; reference_publisher_verification_packet.md; reference_online_metadata_audit.md; reference_publisher_signoff_form.md",
        "WARNING",
        "Online metadata cross-check has no hard failures, but manual publisher-record verification remains required before upload.",
    ),
    Requirement(
        "PREPRINT_REFERENCES",
        GUIDE_URL,
        "Preprint references",
        "Preprints should be clearly marked and replaced by the formal publication if a peer-reviewed version exists.",
        "reference_publisher_verification_packet.md; reference_online_metadata_audit.md; reference_publisher_signoff_form.md",
        "WARNING",
        "Use the reference publisher packet to check arXiv-only and arXiv DOI entries for accepted versions.",
    ),
    Requirement(
        "COVER_LETTER",
        GUIDE_URL,
        "Submitting your manuscript / Cover letter",
        "The cover letter should explain importance and journal fit, and answer SOTA, public dataset, and validation-measure questions.",
        "cover_letter.txt; editorial_manager_upload_index.md",
        "PASS",
        "Add final corresponding-author details before upload.",
    ),
    Requirement(
        "COMPETING_INTERESTS",
        GUIDE_URL,
        "Declaration of competing interests",
        "All authors must disclose financial or personal relationships that could influence the work.",
        "declaration_of_interest.txt; main.tex; author_declaration_signoff_form.md",
        "WARNING",
        "All authors must confirm the declaration in author_declaration_signoff_form.md before upload.",
    ),
    Requirement(
        "FUNDING",
        GUIDE_URL,
        "Funding sources",
        "Funding sources and sponsor role must be disclosed; if there was no specific funding, a no-specific-funding statement is recommended.",
        "submission_metadata_completion_packet.md; author_submission_info_needed.md; main.tex; author_declaration_signoff_form.md",
        "BLOCKER",
        "Funding agency, grant numbers, sponsor role, or no-specific-funding statement must be provided.",
    ),
    Requirement(
        "GENAI_DECLARATION",
        GUIDE_URL,
        "Declaration of generative AI use",
        "Use of generative AI in manuscript preparation must be declared and authors remain responsible for accuracy and originality.",
        "generative_ai_statement.txt; main.tex; author_declaration_signoff_form.md",
        "PASS",
        "Confirm final wording with all authors in author_declaration_signoff_form.md.",
    ),
    Requirement(
        "AUTHOR_APPROVAL",
        GUIDE_URL,
        "Submission declaration / Authorship",
        "The work must be approved by all authors and responsible authorities, and all authors must approve the submitted version.",
        "author_submission_info_needed.md; submission_blocker_audit.md; author_declaration_signoff_form.md",
        "BLOCKER",
        "Final author approval and institutional approval must be recorded in author_declaration_signoff_form.md and in any required institutional system.",
    ),
    Requirement(
        "SUBMISSION_CHECKLIST",
        GUIDE_URL,
        "Submission checklist",
        "Before submission, corresponding-author details, all files, spelling/grammar, reciprocal references, permissions, and APC understanding should be checked.",
        "submission_checklist.md; final_submission_handoff.md; official_requirements_snapshot.md",
        "WARNING",
        "Run final handoff before Editorial Manager upload; repeat the official-page recheck only if uploading after the access date or after a page change.",
    ),
]


def write_csv(rows: list[Requirement]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["item_id", "source", "section", "requirement", "local_evidence", "status", "remaining_action"]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def write_markdown(rows: list[Requirement]) -> None:
    status_counts = {status: sum(1 for row in rows if row.status == status) for status in ["PASS", "PARTIAL", "WARNING", "BLOCKER"]}
    lines = [
        "# Official Requirements Snapshot",
        "",
        f"This snapshot records the official ScienceDirect special-issue and Pattern Recognition guide requirements checked on {ACCESS_DATE}. It is a dated reproducibility artifact for the current package; {FUTURE_RECHECK_POLICY}",
        "",
        "## Official Sources",
        "",
        f"- Special issue page: {SPECIAL_ISSUE_URL}",
        f"- Pattern Recognition guide for authors: {GUIDE_URL}",
        f"- Access date: {ACCESS_DATE}",
        "- Source access mode: MANUAL_WEB_REVIEW_AND_OFFLINE_SNAPSHOT",
        "",
        "## Summary",
        "",
        f"- Snapshot status: {SNAPSHOT_STATUS}",
        "- Official source URLs: 2",
        f"- Requirements tracked: {len(rows)}",
        f"- Local PASS rows: {status_counts['PASS']}",
        f"- Local PARTIAL rows: {status_counts['PARTIAL']}",
        f"- Local WARNING rows: {status_counts['WARNING']}",
        f"- Local BLOCKER rows: {status_counts['BLOCKER']}",
        f"- Final official recheck before upload: {FINAL_RECHECK_STATUS}",
        f"- Future upload recheck policy: {FUTURE_RECHECK_POLICY}",
        "",
        "## Requirement Map",
        "",
        "| ID | Source section | Requirement summary | Local evidence | Status | Remaining action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = [
            f"`{row.item_id}`",
            row.section,
            row.requirement,
            row.local_evidence,
            row.status,
            row.remaining_action,
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    lines.extend(
        [
            "",
            "## Completion Rule",
            "",
            f"This snapshot is complete for the current dated package. The submission remains blocked until author metadata, ethics/funding details, author declaration signoff, final author PDF signoff, manual reference verification, and clinical overlay signoff are completed. {FUTURE_RECHECK_POLICY}",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    write_csv(REQUIREMENTS)
    write_markdown(REQUIREMENTS)
    blockers = [row for row in REQUIREMENTS if row.status == "BLOCKER"]
    warnings = [row for row in REQUIREMENTS if row.status == "WARNING"]
    partial = [row for row in REQUIREMENTS if row.status == "PARTIAL"]
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(
        "Official requirements snapshot: "
        f"tracked={len(REQUIREMENTS)}; blockers={len(blockers)}; "
        f"warnings={len(warnings)}; partial={len(partial)}"
    )


if __name__ == "__main__":
    main()
