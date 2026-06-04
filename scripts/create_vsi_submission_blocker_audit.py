#!/usr/bin/env python3
"""Create a structured audit of unresolved VSI submission blockers."""

from __future__ import annotations

import shutil
import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
OUT = PKG / "submission_blocker_audit.md"
KNOWN_TOOL_DIRS = [Path("/tmp/vsi_tectonic_env/bin")]


@dataclass(frozen=True)
class Evidence:
    rel: str
    line: int
    text: str


@dataclass(frozen=True)
class AuditItem:
    item_id: str
    severity: str
    requirement: str
    evidence: list[Evidence]
    resolution: str
    owner: str


def read_lines(rel: str) -> list[str]:
    path = PKG / rel
    if not path.exists():
        return []
    return path.read_text().splitlines()


def find_hits(rel: str, needles: list[str]) -> list[Evidence]:
    hits: list[Evidence] = []
    for idx, line in enumerate(read_lines(rel), 1):
        for needle in needles:
            if needle in line:
                hits.append(Evidence(rel, idx, " ".join(line.strip().split())))
                break
    return hits


def tool_path(tool: str) -> str:
    found = shutil.which(tool)
    if found:
        return found
    for directory in KNOWN_TOOL_DIRS:
        candidate = directory / tool
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def accepted_backend() -> tuple[str, str]:
    latexmk = tool_path("latexmk")
    if latexmk:
        return "latexmk", latexmk
    tectonic = tool_path("tectonic")
    if tectonic:
        return "tectonic", tectonic
    return "none", ""


def tool_hits() -> list[Evidence]:
    hits: list[Evidence] = []
    backend, _ = accepted_backend()
    if backend == "none":
        hits.append(Evidence("environment", 0, "No accepted TeX backend available: latexmk/pdflatex or Tectonic"))
    return hits


def citation_review_hits() -> list[Evidence]:
    hits = find_hits("reference_publisher_verification_packet.md", ["Packet status: MANUAL_PUBLISHER_REVIEW_REQUIRED"])
    hits.extend(find_hits("citation_metadata_audit.md", ["Remaining Manual Citation Tasks"]))
    hits.extend(
        find_hits(
            "reference_online_metadata_audit.md",
            [
                "Online metadata audit status:",
                "Metadata fetch failures: 0",
                "Hard review rows: 0",
                "Manual publisher verification status: STILL REQUIRED",
            ],
        )
    )
    if hits:
        return hits
    return []


def clinical_overlay_review_hits() -> list[Evidence]:
    hits = find_hits("clinical_overlay_visual_review_packet.md", ["Packet status: CLINICAL_OVERLAY_VISUAL_REVIEW_REQUIRED", "Clinical-owner signoff status: REQUIRED"])
    hits.extend(
        find_hits(
            "clinical_overlay_ai_visual_prescreen.md",
            [
                "AI visual prescreen status:",
                "Visible PHI-like text after AI prescreen:",
                "Clinical-owner signoff status: STILL REQUIRED",
            ],
        )
    )
    hits.extend(
        find_hits(
            "clinical_overlay_signoff_form.md",
            [
                "Signoff status: CLINICAL_OVERLAY_SIGNOFF_REQUIRED",
                "Clinical overlay files requiring signoff:",
                "Blocking signoff rows:",
            ],
        )
    )
    if hits:
        return hits
    return []


def official_requirement_review_hits() -> list[Evidence]:
    hits = find_hits(
        "official_requirements_snapshot.md",
        ["Snapshot status: OFFICIAL_REQUIREMENTS_RECHECK_REQUIRED", "Final official recheck before upload: REQUIRED"],
    )
    if hits:
        return hits
    return []


def author_declaration_review_hits() -> list[Evidence]:
    hits = find_hits(
        "author_declaration_signoff_form.md",
        [
            "Signoff status: AUTHOR_DECLARATION_SIGNOFF_REQUIRED",
            "Declaration signoff checklist rows:",
            "Blocking signoff rows:",
        ],
    )
    if hits:
        return hits
    return []


def evidence_cell(evidence: list[Evidence]) -> str:
    if not evidence:
        return "No local issue detected"
    parts = []
    for item in evidence[:6]:
        loc = item.rel if item.line == 0 else f"{item.rel}:{item.line}"
        snippet = item.text.replace("|", "\\|")
        if len(snippet) > 96:
            snippet = snippet[:93] + "..."
        parts.append(f"`{loc}` {snippet}")
    if len(evidence) > 6:
        parts.append(f"... plus {len(evidence) - 6} more")
    return "<br>".join(parts)


def build_items() -> list[AuditItem]:
    author_hits = []
    author_hits.extend(
        find_hits(
            "main.tex",
            [
                "corresponding.email",
                "Institution to be finalized",
                "city={City}",
                "country={Country}",
            ],
        )
    )
    author_hits.extend(
        find_hits(
            "submission_metadata_template.yaml",
            [
                "email: TODO_REPLACE",
                "orcid: TODO_REPLACE_OR_LEAVE_EMPTY",
                "organization: TODO_REPLACE",
                "city: TODO_REPLACE",
                "country: TODO_REPLACE",
                "address: TODO_REPLACE",
            ],
        )
    )

    ethics_hits = []
    ethics_hits.extend(find_hits("main.tex", ["must be inserted before submission"]))
    ethics_hits.extend(
        find_hits(
            "submission_metadata_template.yaml",
            [
                "approval_body: TODO_REPLACE",
                "approval_number: TODO_REPLACE",
                "consent_or_waiver: TODO_REPLACE",
            ],
        )
    )

    funding_hits = []
    funding_hits.extend(find_hits("main.tex", ["funding information should be finalized"]))
    funding_hits.extend(find_hits("submission_metadata_template.yaml", ["statement: TODO_REPLACE"]))

    contribution_hits = find_hits(
        "submission_metadata_template.yaml",
        [
            "conceptualization: TODO_REPLACE",
            "methodology: TODO_REPLACE",
            "software: TODO_REPLACE",
            "validation: TODO_REPLACE",
            "investigation: TODO_REPLACE",
            "writing_original_draft: TODO_REPLACE",
            "writing_review_editing: TODO_REPLACE",
            "supervision: TODO_REPLACE",
        ],
    )
    contribution_hits.extend(author_declaration_review_hits())

    cover_hits = find_hits("cover_letter.txt", ["Corresponding author details to be finalized"])
    tex_hits = tool_hits()
    tex_hits.extend(
        find_hits(
            "pdf_render_audit.md",
            [
                "PDF render audit status:",
                "Main PDF present: NO",
                "Rendered page count: NOT VERIFIED",
                "Manual rendered review status: REQUIRED_AFTER_COMPILE",
            ],
        )
    )
    tex_hits.extend(
        find_hits(
            "rendered_pdf_visual_prescreen.md",
            [
                "Prescreen status:",
                "Final submitting-author rendered-PDF signoff: STILL REQUIRED",
                "Residual author/institutional placeholders: PRESENT",
                "Residual ethics/funding placeholders: PRESENT",
                "Clinical overlay pixel signoff: STILL REQUIRED",
            ],
        )
    )
    tex_hits.extend(
        find_hits(
            "rendered_pdf_author_signoff_form.md",
            [
                "Signoff status: RENDERED_PDF_AUTHOR_SIGNOFF_REQUIRED",
                "PDF signoff checklist rows:",
                "Blocking signoff rows:",
            ],
        )
    )
    citation_hits = citation_review_hits()
    overlay_hits = clinical_overlay_review_hits()
    official_hits = official_requirement_review_hits()

    return [
        AuditItem(
            "BLOCKER_AUTHOR_METADATA",
            "BLOCKER",
            "Final author list, affiliations, corresponding author email, and address",
            author_hits + cover_hits,
            "Collect approved values in submission_metadata_author_fill_form.md, run metadata-fill-sync, update submission_metadata_template.yaml after approval, apply metadata after approval, then inspect main.tex and cover_letter.txt.",
            "Corresponding author / PI",
        ),
        AuditItem(
            "BLOCKER_ETHICS_CONSENT",
            "BLOCKER",
            "IRB or ethics approval body, approval number or exemption, and consent/waiver language",
            ethics_hits,
            "Collect institutionally approved language in submission_metadata_author_fill_form.md, then run metadata-fill-sync and update ethics fields in submission_metadata_template.yaml after approval.",
            "PI / institutional compliance office",
        ),
        AuditItem(
            "BLOCKER_FUNDING_ACKNOWLEDGEMENTS",
            "BLOCKER",
            "Funding agency, grant numbers, sponsor role, and acknowledgements",
            funding_hits,
            "Collect funding or no-specific-funding text in submission_metadata_author_fill_form.md, then run metadata-fill-sync and update funding fields in submission_metadata_template.yaml after approval.",
            "Corresponding author / PI",
        ),
        AuditItem(
            "BLOCKER_CREDIT_AUTHORSHIP",
            "BLOCKER",
            "Author-specific CRediT roles, declarations, and final author approval",
            contribution_hits,
            "Collect author-approved CRediT roles in submission_metadata_author_fill_form.md, run metadata-fill-sync, update submission_metadata_template.yaml after approval, and record final author/declaration approvals in author_declaration_signoff_form.md.",
            "All authors / corresponding author",
        ),
        AuditItem(
            "BLOCKER_FINAL_TEX_PDF",
            "BLOCKER",
            "Compiled PDF inspection for page count, page numbers, line numbers, tables, figures, and bibliography",
            tex_hits,
            "Compile main.tex in a TeX-enabled environment, inspect the rendered PDF, and record row-level approval in rendered_pdf_author_signoff_form.md before submission.",
            "Submitting author",
        ),
        AuditItem(
            "WARNING_REFERENCE_METADATA_REVIEW",
            "WARNING",
            "Manual publisher-record check for all BibTeX entries",
            citation_hits,
            "Use reference_online_metadata_audit.md as the Crossref/arXiv/DataCite/PublisherURL precheck, verify final BibTeX metadata with reference_publisher_verification_packet.md, then record row-level approval in reference_publisher_signoff_form.md.",
            "Submitting author",
        ),
        AuditItem(
            "WARNING_CLINICAL_OVERLAY_PIXEL_REVIEW",
            "WARNING",
            "Manual pixel-level PHI review for clinical overlay figures",
            overlay_hits,
            "Inspect every queued clinical overlay PNG at full resolution and in the rendered PDF using clinical_overlay_visual_review_packet.md and clinical_overlay_ai_visual_prescreen.md, then record final row-level approval in clinical_overlay_signoff_form.md.",
            "Submitting author",
        ),
        AuditItem(
            "WARNING_OFFICIAL_REQUIREMENTS_RECHECK",
            "WARNING",
            "Final official ScienceDirect special-issue and Pattern Recognition guide recheck before upload",
            official_hits,
            "Reopen the official special-issue page and Pattern Recognition guide only if upload occurs after the recorded access date or if either official page changes before upload.",
            "Submitting author",
        ),
    ]


def main() -> None:
    items = build_items()
    blocker_count = sum(1 for item in items if item.severity == "BLOCKER" and item.evidence)
    warning_count = sum(1 for item in items if item.severity == "WARNING" and item.evidence)
    status = "NOT_SUBMISSION_READY" if blocker_count else "READY_FOR_AUTHOR_FINAL_REVIEW"

    lines = [
        "# Submission Blocker Audit",
        "",
        "This audit converts remaining human and environment dependencies into explicit submission-resolution tasks. It does not invent missing author, ethics, funding, or PDF evidence.",
        "",
        f"- Status: {status}",
        f"- Outstanding blocker count: {blocker_count}",
        f"- Warning count: {warning_count}",
        "- Final verification command after resolution: `make -C manuscript_vsi_biomedical_data release`",
        "",
        "## Blocking Items",
        "",
        "| ID | Severity | Requirement | Evidence | Required resolution | Resolution owner |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        active = bool(item.evidence)
        severity = item.severity if active else "RESOLVED"
        lines.append(
            f"| `{item.item_id}` | {severity} | {item.requirement} | {evidence_cell(item.evidence)} | {item.resolution} | {item.owner} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- BLOCKER rows prevent a real journal upload or a claim that the goal is complete.",
            "- WARNING rows should be resolved before upload but are tracked separately from missing institutional information.",
            "- The manuscript package can remain structurally valid while these external dependencies are unresolved.",
            "",
        ]
    )
    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT}")
    print(f"Outstanding blocker count: {blocker_count}; warning count: {warning_count}")


if __name__ == "__main__":
    main()
