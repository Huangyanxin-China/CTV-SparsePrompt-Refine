#!/usr/bin/env python3
"""Create the final handoff checklist for VSI submission.

The handoff intentionally keeps unresolved author, ethics, funding, reference,
figure-review, and PDF dependencies visible. It is the last operational bridge
between the generated source package and a real Editorial Manager upload.
"""

from __future__ import annotations

import csv
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "final_submission_handoff.md"
CSV_OUT = ROOT / "reports" / "vsi_final_submission_handoff_20260531.csv"
KNOWN_TOOL_DIRS = [Path("/tmp/vsi_tectonic_env/bin")]


@dataclass(frozen=True)
class Gate:
    name: str
    status: str
    evidence: str
    required_action: str
    owner: str


def read(rel: str) -> str:
    path = ROOT / rel if rel.startswith(("reports/", "scripts/")) else PKG / rel
    if not path.exists():
        return ""
    return path.read_text()


def find_line(text: str, pattern: str) -> str:
    regex = re.compile(pattern, re.I)
    for line in text.splitlines():
        if regex.search(line):
            return " ".join(line.strip().split())
    return "not found"


def parse_int_line(text: str, label: str) -> int | None:
    match = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", text, re.I)
    return int(match.group(1)) if match else None


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


def status_label(ok: bool, blocked: bool = False, warning: bool = False) -> str:
    if blocked:
        return "BLOCKER"
    if warning:
        return "WARNING"
    return "PASS" if ok else "MISSING"


def build_gates() -> list[Gate]:
    blocker = read("submission_blocker_audit.md")
    metadata_plan = read("metadata_application_plan.md")
    metadata_packet = read("submission_metadata_completion_packet.md")
    metadata_fill_form = read("submission_metadata_author_fill_form.md")
    metadata_fill_sync = read("submission_metadata_fill_form_sync.md")
    metadata_dryrun = read("metadata_pipeline_dry_run_audit.md")
    metadata_lock = read("submission_metadata_lock_audit.md")
    author_signoff = read("author_declaration_signoff_form.md")
    tex_audit = read("tex_compile_readiness_audit.md")
    pdf_handoff = read("pdf_compilation_handoff.md")
    pdf_render = read("pdf_render_audit.md")
    pdf_prescreen = read("rendered_pdf_visual_prescreen.md")
    pdf_signoff = read("rendered_pdf_author_signoff_form.md")
    citation = read("citation_metadata_audit.md")
    refids = read("reference_identifier_audit.md")
    ref_publisher = read("reference_publisher_verification_packet.md")
    ref_online = read("reference_online_metadata_audit.md")
    ref_signoff = read("reference_publisher_signoff_form.md")
    figure = read("figure_privacy_integrity_audit.md")
    overlay_packet = read("clinical_overlay_visual_review_packet.md")
    overlay_prescreen = read("clinical_overlay_ai_visual_prescreen.md")
    overlay_signoff = read("clinical_overlay_signoff_form.md")
    external = read("external_validity_public_data_audit.md")
    split = read("validation_split_leakage_audit.md")
    official = read("official_requirements_snapshot.md")
    initial_delivery = read("initial_draft_delivery_handoff.md")
    initial_draft = read("current_experiment_paper_draft_20260601.md")

    outstanding = parse_int_line(blocker, "Outstanding blocker count")
    metadata_blockers = parse_int_line(metadata_plan, "Blocking metadata fields")
    lock_blockers = parse_int_line(metadata_lock, "Metadata field blockers")
    missing_tex = [tool for tool in ["pdflatex", "latexmk", "kpsewhich"] if tool_path(tool) == ""]
    backend, backend_path = accepted_backend()
    pdf_artifact_ready = (
        "PDF render audit status: READY_FOR_MANUAL_RENDERED_PDF_REVIEW" in pdf_render
        and "PDF handoff status: READY_FOR_RENDERED_PDF_INSPECTION" in pdf_handoff
    )
    manual_pdf_required = "Manual rendered review status: REQUIRED_AFTER_COMPILE" in pdf_render
    prescreen_pass = (
        "Prescreen status: AUTOMATED_RENDERED_PDF_PRESCREEN_PASS_WITH_RESIDUAL_SIGNOFF_REQUIRED" in pdf_prescreen
        or "Prescreen status: AI_RENDERED_PDF_PRESCREEN_PASS_WITH_RESIDUAL_SIGNOFF_REQUIRED" in pdf_prescreen
    )
    initial_draft_ready = (
        "Draft delivery status: INITIAL_DRAFT_DELIVERED" in initial_delivery
        and "current_experiment_paper_draft_20260601.md" in initial_delivery
        and "main.tex" in initial_delivery
        and "Draft status: initial manuscript draft based on current completed experiments" in initial_draft
    )

    gates = [
        Gate(
            "Initial draft delivery",
            status_label(initial_draft_ready),
            f"{find_line(initial_delivery, r'Draft delivery status:')} ; package Markdown draft: {'present' if initial_draft else 'missing'} ; {find_line(initial_delivery, r'Not claimed:')}",
            "Use initial_draft_delivery_handoff.md as the current draft-delivery boundary; later human metadata and final signoff remain part of the submission workflow.",
            "Manuscript owner",
        ),
        Gate(
            "Author, ethics, funding, and CRediT metadata",
            status_label(False, blocked=(metadata_blockers or 0) > 0 or (lock_blockers or 0) > 0),
            f"{find_line(metadata_packet, r'Packet status:')} ; {find_line(metadata_packet, r'Human fill form:')} ; {find_line(metadata_fill_form, r'Required fields still blocked:')} ; {find_line(metadata_fill_sync, r'Sync status:')} ; metadata dry-run: {find_line(metadata_dryrun, r'Status:')} ; {find_line(metadata_lock, r'Metadata field blockers:')}",
            "Use submission_metadata_author_fill_form.md to collect approved values, run metadata-fill-sync, apply the YAML sync after approval, then rerun metadata, metadata-lock, and metadata-apply-plan.",
            "Corresponding author / PI",
        ),
        Gate(
            "Author-approved metadata application",
            status_label(False, blocked="Files modified: NO" in metadata_plan),
            find_line(metadata_plan, r'Apply command after final author approval'),
            "After metadata approval, run python scripts/apply_vsi_submission_metadata.py --apply and inspect main.tex, cover_letter.txt, and credit_author_statement.txt.",
            "Corresponding author / submitting author",
        ),
        Gate(
            "Author declarations and final approval",
            status_label(False, blocked="AUTHOR_DECLARATION_SIGNOFF_REQUIRED" in author_signoff),
            f"{find_line(author_signoff, r'Signoff status:')} ; {find_line(author_signoff, r'Declaration signoff checklist rows:')} ; {find_line(author_signoff, r'Blocking signoff rows:')} ; {find_line(author_signoff, r'Source metadata form:')}",
            "After metadata and declaration text are finalized, record row-level author, declaration, and responsible-authority approvals in author_declaration_signoff_form.md.",
            "All authors / corresponding author",
        ),
        Gate(
            "Rendered PDF compile and inspection",
            status_label(False, blocked=(not pdf_artifact_ready) or manual_pdf_required or "RENDERED_PDF_AUTHOR_SIGNOFF_REQUIRED" in pdf_signoff),
            f"{find_line(pdf_handoff, r'PDF handoff status:')} ; {find_line(pdf_render, r'PDF render audit status:')} ; rendered visual prescreen: {'PASS_WITH_SIGNOFF_REQUIRED' if prescreen_pass else 'not found'} ; {find_line(pdf_signoff, r'Signoff status:')} ; {find_line(pdf_signoff, r'Blocking signoff rows:')} ; accepted backend: {backend} ({backend_path if backend_path else 'none'}) ; legacy TeX tools missing: {', '.join(missing_tex) if missing_tex else 'none'}",
            "Use rendered_pdf_visual_prescreen.md and pdf_compilation_handoff.md, then record final submitting-author PDF decisions in rendered_pdf_author_signoff_form.md after metadata edits; rerun make -C manuscript_vsi_biomedical_data pdf-render-compile after any source change.",
            "Submitting author",
        ),
        Gate(
            "Publisher-record reference review",
            status_label(True, warning="Remaining Manual Citation Tasks" in citation or "REFERENCE_PUBLISHER_SIGNOFF_REQUIRED" in ref_signoff),
            f"{find_line(ref_publisher, r'Packet status:')} ; {find_line(ref_publisher, r'Entries queued:')} ; {find_line(refids, r'Identifier failures:')} ; {find_line(ref_online, r'Online metadata audit status:')} ; {find_line(ref_online, r'Hard review rows:')} ; {find_line(ref_signoff, r'Signoff status:')} ; {find_line(ref_signoff, r'Blocking signoff rows:')}",
            "Use reference_online_metadata_audit.md as the online metadata precheck, then manually verify every BibTeX entry with reference_publisher_verification_packet.md and record final decisions in reference_publisher_signoff_form.md before upload.",
            "Submitting author",
        ),
        Gate(
            "Clinical figure visual PHI review",
            status_label(True, warning="manual visual" in figure.lower() or "Manual visual review status: REQUIRED" in overlay_packet or "CLINICAL_OVERLAY_SIGNOFF_REQUIRED" in overlay_signoff),
            f"{find_line(overlay_packet, r'Packet status:')} ; {find_line(overlay_packet, r'Clinical overlay files queued:')} ; {find_line(overlay_prescreen, r'AI visual prescreen status:')} ; {find_line(overlay_prescreen, r'Visible PHI-like text after AI prescreen:')} ; {find_line(overlay_signoff, r'Signoff status:')} ; {find_line(overlay_signoff, r'Blocking signoff rows:')} ; {find_line(figure, r'Filename PHI hits:')} ; {find_line(figure, r'Metadata PHI hits:')}",
            "Use clinical_overlay_visual_review_packet.md and clinical_overlay_ai_visual_prescreen.md to manually inspect clinical overlay pixels, then record final full-resolution PNG and rendered-PDF decisions in clinical_overlay_signoff_form.md before upload.",
            "Submitting author / clinical data owner",
        ),
        Gate(
            "Official special-issue and guide recheck",
            status_label(True, warning="Final official recheck before upload: REQUIRED" in official),
            f"{find_line(official, r'Snapshot status:')} ; {find_line(official, r'Final official recheck before upload:')} ; {find_line(official, r'Official source URLs:')}",
            "Use official_requirements_snapshot.md as the local checklist; repeat the official-page recheck if uploading after the recorded access date or if either official page changes.",
            "Submitting author",
        ),
        Gate(
            "External validity and claim boundary",
            status_label("PASS_WITH_DISCLOSED_LIMITATION" in external and "PASS_WITH_SCAN_LEVEL_LIMITATION" in split),
            f"{find_line(external, r'Status:')} ; {find_line(split, r'Status:')} ; {find_line(split, r'31 scans from 21 unique patients')}",
            "Keep public-dataset generalization, patient-external validation, and fully automatic CT-to-CTV claims out of the final submission unless new evidence is added.",
            "Manuscript owner",
        ),
        Gate(
            "Final release archive",
            status_label(False, blocked=(outstanding or 0) > 0),
            find_line(blocker, r'Outstanding blocker count:'),
            "After all gates above are resolved, rerun make -C manuscript_vsi_biomedical_data release and confirm the verifier reports READY.",
            "Submitting author",
        ),
    ]
    return gates


def write_csv(gates: list[Gate]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["gate", "status", "evidence", "required_action", "owner"])
        writer.writeheader()
        for gate in gates:
            writer.writerow(
                {
                    "gate": gate.name,
                    "status": gate.status,
                    "evidence": gate.evidence,
                    "required_action": gate.required_action,
                    "owner": gate.owner,
                }
            )


def write_markdown(gates: list[Gate]) -> None:
    blocker_count = sum(1 for gate in gates if gate.status == "BLOCKER")
    warning_count = sum(1 for gate in gates if gate.status == "WARNING")
    decision = "READY_FOR_UPLOAD" if blocker_count == 0 else "NOT_READY_FOR_UPLOAD"
    lines = [
        "# Final Submission Handoff",
        "",
        "This handoff is the operational checklist for moving from the generated TeX source package to a real Editorial Manager upload. It records what must be done by humans or in a TeX-enabled environment and does not mark unresolved dependencies as complete.",
        "",
        "## Summary",
        "",
        f"- Handoff decision: {decision}",
        f"- Blocking handoff gates: {blocker_count}",
        f"- Warning handoff gates: {warning_count}",
        "- Final release command after all gates pass: `make -C manuscript_vsi_biomedical_data release`",
        "- Final PDF command in a TeX-enabled environment: `make -C manuscript_vsi_biomedical_data pdf`",
        "- Final PDF compile/audit command in a TeX-enabled environment: `make -C manuscript_vsi_biomedical_data pdf-render-compile`",
        "- Rendered PDF visual prescreen: `rendered_pdf_visual_prescreen.md`",
        "- Rendered PDF author signoff form: `rendered_pdf_author_signoff_form.md`",
        "- Author declaration signoff form: `author_declaration_signoff_form.md`",
        "- Concise human completion quickstart: `human_completion_quickstart.md`",
        "- Initial draft delivery handoff: `initial_draft_delivery_handoff.md`",
        "- Fill-form YAML sync command after author approval: `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply`",
        "- Final metadata apply command after author approval: `python scripts/apply_vsi_submission_metadata.py --apply`",
        "",
        "## Gate Table",
        "",
        "| Gate | Status | Evidence | Required action | Owner |",
        "| --- | --- | --- | --- | --- |",
    ]
    for gate in gates:
        cells = [
            gate.name,
            gate.status,
            gate.evidence,
            gate.required_action,
            gate.owner,
        ]
        escaped = [cell.replace("|", "\\|") for cell in cells]
        lines.append("| " + " | ".join(escaped) + " |")

    lines.extend(
        [
            "",
            "## Required Sequence",
            "",
            "1. Fill and approve `submission_metadata_author_fill_form.md` with final author, affiliation, ethics, funding, and CRediT details.",
            "   Use `submission_metadata_completion_packet.md` as the audit checklist.",
            "2. Run `make -C manuscript_vsi_biomedical_data metadata-fill-sync` to audit the form, then run `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply` after approval to update `submission_metadata_template.yaml`.",
            "3. Run `make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan` and confirm no metadata blockers remain.",
            "4. Run `python scripts/apply_vsi_submission_metadata.py --apply` only after final author approval, then inspect `main.tex`, `cover_letter.txt`, and `credit_author_statement.txt`.",
            "5. Record author, declaration, and responsible-authority approvals in `author_declaration_signoff_form.md` after metadata and declaration text are final.",
            "6. Compile and audit the manuscript with `make -C manuscript_vsi_biomedical_data pdf-render-compile` in a TeX-enabled environment, then inspect the rendered PDF.",
            "   Use `pdf_compilation_handoff.md`, `rendered_pdf_visual_prescreen.md`, and `rendered_pdf_author_signoff_form.md` as rendered-PDF inspection records.",
            "7. Complete online reference metadata precheck with `reference_online_metadata_audit.md`, manual publisher-record reference review with `reference_publisher_verification_packet.md`, final reference signoff in `reference_publisher_signoff_form.md`, and clinical overlay pixel review with `clinical_overlay_visual_review_packet.md`, using `clinical_overlay_ai_visual_prescreen.md` as a non-signoff precheck record and `clinical_overlay_signoff_form.md` as the final row-level overlay signoff record.",
            "8. Reopen the official ScienceDirect special-issue page and Pattern Recognition guide, then compare them against `official_requirements_snapshot.md`.",
            "9. Rerun `make -C manuscript_vsi_biomedical_data release` and require `reports/vsi_manuscript_package_verification.md` to report `Status: **READY**` before upload.",
            "",
            "## Non-Substitutable Evidence",
            "",
            "- Archive integrity is not a substitute for author approval or rendered PDF inspection.",
            "- Source-level TeX checks are not a substitute for a compiled PDF.",
            "- A PDF render audit is not a substitute for human inspection of layout, line numbers, tables, figures, bibliography, and clinical overlay pixels.",
            "- A rendered PDF visual prescreen reduces layout uncertainty but is not final submitting-author signoff.",
            "- A rendered PDF author signoff form is required to close the final PDF blocker.",
            "- DOI/arXiv identifier coverage is not a substitute for manual publisher-record verification.",
            "- Online Crossref/arXiv/DataCite/PublisherURL metadata checks are not a substitute for final author approval of every reference row.",
            "- A reference publisher verification packet is a review queue, not evidence that publisher records have already been checked.",
            "- A reference publisher signoff form is required to close the manual reference-review warning.",
            "- A clinical overlay visual review packet is a review queue, not evidence that clinical-owner pixel review has already been signed off.",
            "- A clinical overlay AI visual prescreen is not a substitute for OCR, clinical-owner signoff, or rendered-PDF inspection.",
            "- A clinical overlay signoff form is required to close the manual clinical overlay pixel-review warning.",
            "- The official requirements snapshot was rechecked for the current dated package; repeat it if upload occurs after the recorded access date or if either official page changes.",
            "- The validation split/leakage audit is not a substitute for future fully patient-grouped external validation.",
            "- Metadata dry-run planning is not a substitute for final author-approved metadata application.",
            "- An author declaration signoff form is required to close final author approval, declaration, and responsible-authority approval blockers.",
            "- Initial-draft delivery is not a substitute for final journal submission readiness.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    gates = build_gates()
    write_csv(gates)
    write_markdown(gates)
    blocker_count = sum(1 for gate in gates if gate.status == "BLOCKER")
    warning_count = sum(1 for gate in gates if gate.status == "WARNING")
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Final submission handoff: blockers={blocker_count}; warnings={warning_count}")


if __name__ == "__main__":
    main()
