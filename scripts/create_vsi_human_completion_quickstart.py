#!/usr/bin/env python3
"""Create a concise human completion quickstart for the VSI package."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "human_completion_quickstart.md"
CSV_OUT = ROOT / "reports" / "vsi_human_completion_quickstart_20260601.csv"


@dataclass(frozen=True)
class QuickRow:
    gate: str
    remaining: str
    file_to_edit: str
    validation_command: str
    completion_evidence: str
    owner: str


def read(rel: str) -> str:
    path = PKG / rel
    return path.read_text() if path.exists() else ""


def line_value(text: str, label: str, default: str = "not found") -> str:
    match = re.search(rf"^\s*-\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text, re.M)
    if match:
        return match.group(1).strip()
    match = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*[^|]+\|\s*([^|]+)\|", text)
    if match:
        return match.group(1).strip()
    return default


def first_line(text: str, needle: str, default: str = "not found") -> str:
    for line in text.splitlines():
        if needle in line:
            return " ".join(line.strip().split())
    return default


def build_rows() -> list[QuickRow]:
    metadata_packet = read("submission_metadata_completion_packet.md")
    metadata_form = read("submission_metadata_author_fill_form.md")
    metadata_sync = read("submission_metadata_fill_form_sync.md")
    author_signoff = read("author_declaration_signoff_form.md")
    pdf_signoff = read("rendered_pdf_author_signoff_form.md")
    reference_signoff = read("reference_publisher_signoff_form.md")
    overlay_signoff = read("clinical_overlay_signoff_form.md")
    blocker = read("submission_blocker_audit.md")

    metadata_remaining = line_value(metadata_packet, "Required metadata blockers")
    form_remaining = line_value(metadata_form, "Required fields still blocked")
    sync_blocking = line_value(metadata_sync, "Blocking rows")
    author_blocking = line_value(author_signoff, "Blocking signoff rows")
    pdf_blocking = line_value(pdf_signoff, "Blocking signoff rows")
    reference_blocking = line_value(reference_signoff, "Blocking signoff rows")
    overlay_blocking = line_value(overlay_signoff, "Blocking signoff rows")
    outstanding = line_value(blocker, "Outstanding blocker count")

    return [
        QuickRow(
            "Author, affiliation, ethics, funding, and CRediT metadata",
            f"{metadata_remaining} required metadata blockers; fill form reports {form_remaining} blocked required fields; sync blocking rows {sync_blocking}",
            "submission_metadata_author_fill_form.md",
            "make -C manuscript_vsi_biomedical_data metadata-fill-sync",
            "submission_metadata_fill_form_sync.md reports READY_TO_APPLY, then submission_metadata_template.yaml is updated with --apply after author approval",
            "Corresponding author / PI / all authors",
        ),
        QuickRow(
            "Apply approved metadata into manuscript files",
            f"{line_value(read('metadata_application_plan.md'), 'Status')} with {line_value(read('metadata_application_plan.md'), 'Blocking metadata fields')} blocking metadata fields",
            "submission_metadata_template.yaml",
            "make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan",
            "metadata_application_plan.md reports no blockers, then python scripts/apply_vsi_submission_metadata.py --apply updates main.tex, cover_letter.txt, and credit_author_statement.txt",
            "Corresponding author / submitting author",
        ),
        QuickRow(
            "Author declarations and final approval",
            f"{author_blocking} blocking declaration signoff rows",
            "author_declaration_signoff_form.md",
            "make -C manuscript_vsi_biomedical_data author-signoff",
            "author_declaration_signoff_form.md reports AUTHOR_DECLARATION_SIGNOFF_COMPLETE",
            "All authors / corresponding author",
        ),
        QuickRow(
            "Rendered PDF inspection and signoff",
            f"{pdf_blocking} blocking rendered-PDF signoff rows",
            "rendered_pdf_author_signoff_form.md",
            "make -C manuscript_vsi_biomedical_data pdf-render-compile pdf-prescreen pdf-signoff",
            "rendered_pdf_author_signoff_form.md reports RENDERED_PDF_AUTHOR_SIGNOFF_COMPLETE for the exact PDF intended for upload",
            "Submitting author",
        ),
        QuickRow(
            "Reference publisher-record signoff",
            f"{reference_blocking} blocking reference signoff rows",
            "reference_publisher_signoff_form.md",
            "make -C manuscript_vsi_biomedical_data ref-online ref-signoff",
            "reference_publisher_signoff_form.md reports REFERENCE_PUBLISHER_SIGNOFF_COMPLETE",
            "Submitting author",
        ),
        QuickRow(
            "Clinical overlay pixel signoff",
            f"{overlay_blocking} blocking clinical-overlay signoff rows",
            "clinical_overlay_signoff_form.md",
            "make -C manuscript_vsi_biomedical_data overlay-prescreen overlay-signoff",
            "clinical_overlay_signoff_form.md reports CLINICAL_OVERLAY_SIGNOFF_COMPLETE after full-resolution PNG and rendered-PDF review",
            "Submitting author / clinical data owner",
        ),
        QuickRow(
            "Final release gate",
            f"{outstanding} outstanding submission blockers",
            "final_submission_handoff.md",
            "make -C manuscript_vsi_biomedical_data release",
            "reports/vsi_manuscript_package_verification.md reports READY and objective_completion_audit.md reports COMPLETE",
            "Submitting author",
        ),
    ]


def write_csv(rows: list[QuickRow]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "gate",
                "remaining",
                "file_to_edit",
                "validation_command",
                "completion_evidence",
                "owner",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def write_markdown(rows: list[QuickRow]) -> None:
    blocker = read("submission_blocker_audit.md")
    pdf_render = read("pdf_render_audit.md")
    external = read("external_validity_public_data_audit.md")
    split = read("validation_split_leakage_audit.md")
    metadata_dryrun = read("metadata_pipeline_dry_run_audit.md")

    lines = [
        "# Human Completion Quickstart",
        "",
        "This is the shortest handoff for turning the generated manuscript package into a real upload candidate. It does not invent author, ethics, funding, CRediT, reference, PDF, or clinical-review approvals.",
        "",
        "## Current State",
        "",
        f"- Outstanding blocker count: {line_value(blocker, 'Outstanding blocker count')}",
        f"- PDF page count: {line_value(pdf_render, 'Rendered page count')}",
        f"- External-validity audit: {line_value(external, 'Status')}",
        f"- Validation split/leakage audit: {line_value(split, 'Status')}",
        f"- Metadata pipeline dry-run audit: {line_value(metadata_dryrun, 'Status')}",
        "- Manual values are preserved when the fill/signoff forms are regenerated by their generator scripts.",
        "- Do not run `--apply` commands until the corresponding author, PI/compliance office, grants office, and all required authors have approved the entered values.",
        "",
        "## Minimal Completion Sequence",
        "",
        "| Step | Gate | Remaining now | Edit this file | Validate with | Completion evidence | Owner |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for idx, row in enumerate(rows, 1):
        cells = [
            str(idx),
            row.gate,
            row.remaining,
            f"`{row.file_to_edit}`",
            f"`{row.validation_command}`",
            row.completion_evidence,
            row.owner,
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## Apply Commands After Approval",
            "",
            "Run these only after the relevant human approvals exist:",
            "",
            "```bash",
            "python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply",
            "make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan",
            "python scripts/apply_vsi_submission_metadata.py --apply",
            "make -C manuscript_vsi_biomedical_data release",
            "```",
            "",
            "## Completion Rule",
            "",
            "- The package is not upload-ready until `submission_blocker_audit.md` reports zero outstanding blockers.",
            "- The active objective is not complete until `objective_completion_audit.md` reports `Completion decision: COMPLETE` and `reports/vsi_manuscript_package_verification.md` reports `Status: **READY**`.",
            "- Keep the 31 scan-level test scans from 21 patients language unchanged unless new validation evidence is added.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Human completion quickstart rows: {len(rows)}")


if __name__ == "__main__":
    main()
