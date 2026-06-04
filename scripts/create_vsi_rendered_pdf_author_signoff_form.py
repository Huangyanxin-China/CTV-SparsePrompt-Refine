#!/usr/bin/env python3
"""Create a preserved human signoff form for final rendered-PDF review."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "rendered_pdf_author_signoff_form.md"
CSV_OUT = ROOT / "reports" / "vsi_rendered_pdf_author_signoff_20260601.csv"

APPROVED_DECISIONS = {"APPROVED_NO_CHANGES", "APPROVED_AFTER_CORRECTION"}
OPEN_DECISIONS = {"", "NEEDS_CORRECTION_OR_RECOMPILE", "BLOCKED_BY_METADATA_OR_OTHER_SIGNOFF"}
ALLOWED_DECISIONS = APPROVED_DECISIONS | OPEN_DECISIONS
YES_VALUES = {"YES", "Y", "TRUE", "CHECKED"}


CHECKS = [
    {
        "key": "rendered_page_count",
        "label": "Rendered page count",
        "required_check": "Confirm the opened PDF has 20-35 rendered pages and matches the automated page count.",
        "evidence_needles": [
            ("pdf_render_audit.md", "Rendered page count:"),
            ("rendered_pdf_visual_prescreen.md", "Rendered page count:"),
            ("rendered_pdf_visual_prescreen.md", "Page-count status: PASS"),
        ],
    },
    {
        "key": "page_numbering",
        "label": "Page numbering",
        "required_check": "Confirm page numbers are visible and ordered throughout the opened PDF.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Page-number visibility: PASS"),
        ],
    },
    {
        "key": "line_numbering",
        "label": "Line numbering",
        "required_check": "Confirm manuscript line numbers are visible on body pages.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Line-number visibility: PASS"),
        ],
    },
    {
        "key": "body_layout",
        "label": "Body layout",
        "required_check": "Confirm the PDF is single-column, double-spaced, readable, and not clipped.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Body layout: PASS"),
        ],
    },
    {
        "key": "tables",
        "label": "Tables",
        "required_check": "Inspect every rendered table for readable text, non-overlap, and correct placement.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Table readability: PASS"),
        ],
    },
    {
        "key": "figures",
        "label": "Figures",
        "required_check": "Inspect every rendered figure, caption, legend, and panel label for readability and correct placement.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Figure readability: PASS"),
        ],
    },
    {
        "key": "bibliography_and_citations",
        "label": "Bibliography and citations",
        "required_check": "Confirm numeric citations, bibliography numbering, and absence of unresolved markers in the opened PDF.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Bibliography rendering: PASS"),
            ("rendered_pdf_visual_prescreen.md", "Unresolved citation/reference markers: none detected"),
        ],
    },
    {
        "key": "author_affiliation_metadata",
        "label": "Author and affiliation metadata",
        "required_check": "Confirm author names, affiliations, corresponding email, and address are final in the rendered PDF.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Residual author/institutional placeholders: PRESENT"),
            ("submission_metadata_lock_audit.md", "Status: NOT_READY_FOR_METADATA_LOCK"),
        ],
        "automated_state": "BLOCKED_CURRENTLY_PLACEHOLDER_PRESENT",
    },
    {
        "key": "ethics_funding_metadata",
        "label": "Ethics and funding metadata",
        "required_check": "Confirm ethics, consent/waiver, funding, acknowledgements, and declarations are final in the rendered PDF.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Residual ethics/funding placeholders: PRESENT"),
            ("submission_metadata_lock_audit.md", "Status: NOT_READY_FOR_METADATA_LOCK"),
        ],
        "automated_state": "BLOCKED_CURRENTLY_PLACEHOLDER_PRESENT",
    },
    {
        "key": "clinical_overlay_signoff",
        "label": "Clinical overlay pixel signoff",
        "required_check": "Confirm clinical overlay pixel review has been signed off for full-resolution PNGs and rendered PDF placement.",
        "evidence_needles": [
            ("clinical_overlay_signoff_form.md", "Signoff status: CLINICAL_OVERLAY_SIGNOFF_REQUIRED"),
            ("rendered_pdf_visual_prescreen.md", "Clinical overlay pixel signoff: STILL REQUIRED"),
        ],
        "automated_state": "BLOCKED_CURRENTLY_OVERLAY_SIGNOFF_REQUIRED",
    },
    {
        "key": "final_submitting_author_approval",
        "label": "Final submitting-author approval",
        "required_check": "Confirm the submitting author approves the exact final PDF intended for upload after all metadata and signoff changes.",
        "evidence_needles": [
            ("rendered_pdf_visual_prescreen.md", "Final submitting-author rendered-PDF signoff: STILL REQUIRED"),
        ],
    },
]


def read(rel: str) -> str:
    path = PKG / rel
    if not path.exists():
        return ""
    return path.read_text()


def first_evidence_line(rel: str, needle: str) -> str:
    for line in read(rel).splitlines():
        if needle in line:
            return " ".join(line.strip().split())
    return "not found"


def parse_existing_form() -> dict[str, dict[str, str]]:
    if not MD_OUT.exists():
        return {}
    text = MD_OUT.read_text()
    existing: dict[str, dict[str, str]] = {}
    section_pattern = re.compile(r"^### `([^`]+)`\n(.*?)(?=^### `|^## |\Z)", re.M | re.S)
    field_patterns = {
        "decision": re.compile(r"- Final rendered-PDF decision:\n\n```text\n(.*?)\n```", re.S),
        "reviewer": re.compile(r"- Reviewer and review date:\n\n```text\n(.*?)\n```", re.S),
        "opened_pdf": re.compile(r"- Opened final PDF checked:\n\n```text\n(.*?)\n```", re.S),
        "corrections": re.compile(r"- Corrections or recompilation notes:\n\n```text\n(.*?)\n```", re.S),
    }
    for match in section_pattern.finditer(text):
        key = match.group(1)
        body = match.group(2)
        existing[key] = {}
        for name, pattern in field_patterns.items():
            value_match = pattern.search(body)
            existing[key][name] = value_match.group(1).strip() if value_match else ""
    return existing


def checked(value: str) -> bool:
    return value.strip().upper() in YES_VALUES


def decision_status(decision: str, reviewer: str, opened_pdf: str, corrections: str) -> tuple[str, str]:
    normalized = decision.strip()
    if normalized not in ALLOWED_DECISIONS:
        return (
            "BLOCKER_INVALID_DECISION",
            "Use APPROVED_NO_CHANGES, APPROVED_AFTER_CORRECTION, NEEDS_CORRECTION_OR_RECOMPILE, or BLOCKED_BY_METADATA_OR_OTHER_SIGNOFF.",
        )
    if normalized in APPROVED_DECISIONS:
        if not reviewer.strip():
            return "BLOCKER_REVIEWER_MISSING", "Record reviewer name/initials and review date."
        if not checked(opened_pdf):
            return "BLOCKER_FINAL_PDF_NOT_OPENED", "Record YES only after opening and inspecting the final PDF."
        if normalized == "APPROVED_AFTER_CORRECTION" and not corrections.strip():
            return "BLOCKER_CORRECTION_NOTE_MISSING", "Describe the correction and recompilation/reinspection performed."
        return "APPROVED", "No further rendered-PDF action for this row."
    if normalized == "NEEDS_CORRECTION_OR_RECOMPILE":
        return "BLOCKER_NEEDS_CORRECTION_OR_RECOMPILE", "Correct the manuscript, recompile/audit the PDF, then re-review this row."
    if normalized == "BLOCKED_BY_METADATA_OR_OTHER_SIGNOFF":
        return "BLOCKER_METADATA_OR_OTHER_SIGNOFF", "Resolve metadata, reference, clinical overlay, or other required signoff before final PDF approval."
    return "BLOCKER_PDF_REVIEW_REQUIRED", "Open the final PDF, inspect this item, and record an approved final decision."


def build_rows(existing: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in CHECKS:
        key = item["key"]
        saved = existing.get(key, {})
        decision = saved.get("decision", "").strip()
        reviewer = saved.get("reviewer", "").strip()
        opened_pdf = saved.get("opened_pdf", "").strip()
        corrections = saved.get("corrections", "").strip()
        status, action = decision_status(decision, reviewer, opened_pdf, corrections)
        evidence = "; ".join(
            f"{rel}: {first_evidence_line(rel, needle)}" for rel, needle in item["evidence_needles"]
        )
        rows.append(
            {
                "key": key,
                "label": item["label"],
                "required_check": item["required_check"],
                "automated_evidence_state": item.get("automated_state", "PRESCREEN_AVAILABLE_REQUIRES_HUMAN_CONFIRMATION"),
                "evidence": evidence,
                "final_decision": decision,
                "reviewer_and_date_present": "YES" if reviewer else "NO",
                "opened_final_pdf_checked": "YES" if checked(opened_pdf) else "NO",
                "correction_note_present": "YES" if corrections else "NO",
                "signoff_status": status,
                "required_action": action,
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "key",
        "label",
        "required_check",
        "automated_evidence_state",
        "evidence",
        "final_decision",
        "reviewer_and_date_present",
        "opened_final_pdf_checked",
        "correction_note_present",
        "signoff_status",
        "required_action",
    ]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def code_block(text: str) -> list[str]:
    return ["```text", text, "```"]


def write_markdown(rows: list[dict[str, str]], existing: dict[str, dict[str, str]]) -> None:
    blocking_rows = [row for row in rows if row["signoff_status"] != "APPROVED"]
    approved_rows = [row for row in rows if row["signoff_status"] == "APPROVED"]
    status = "RENDERED_PDF_AUTHOR_SIGNOFF_COMPLETE" if rows and not blocking_rows else "RENDERED_PDF_AUTHOR_SIGNOFF_REQUIRED"

    lines = [
        "# Rendered PDF Author Signoff Form",
        "",
        "This form records final submitting-author review of the exact rendered PDF intended for upload. It preserves previously entered values when regenerated and does not replace metadata, reference, or clinical overlay signoff forms.",
        "",
        "## Summary",
        "",
        f"- Signoff status: {status}",
        f"- PDF signoff checklist rows: {len(rows)}",
        f"- Approved PDF signoff rows: {len(approved_rows)}",
        f"- Blocking signoff rows: {len(blocking_rows)}",
        "- PDF source: `main.pdf`",
        "- Render audit source: `pdf_render_audit.md`",
        "- Visual prescreen source: `rendered_pdf_visual_prescreen.md`",
        "- Clinical overlay signoff dependency: `clinical_overlay_signoff_form.md`",
        "- Machine-readable signoff audit: `reports/vsi_rendered_pdf_author_signoff_20260601.csv`",
        "- Allowed final decisions: `APPROVED_NO_CHANGES`, `APPROVED_AFTER_CORRECTION`, `NEEDS_CORRECTION_OR_RECOMPILE`, `BLOCKED_BY_METADATA_OR_OTHER_SIGNOFF`",
        "- Regeneration command: `make -C manuscript_vsi_biomedical_data pdf-signoff`",
        "",
        "## Signoff Status Table",
        "",
        "| Row | Required check | Final decision | Opened PDF checked | Signoff status | Required action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{md_escape(row['key'])}`",
                    md_escape(row["label"]),
                    f"`{md_escape(row['final_decision'] or 'BLANK')}`",
                    f"`{md_escape(row['opened_final_pdf_checked'])}`",
                    f"`{md_escape(row['signoff_status'])}`",
                    md_escape(row["required_action"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Per-Check Human Signoff",
            "",
            "For each row, open `main.pdf` after final metadata, figure, bibliography, and signoff edits. Use `YES` for the opened-PDF field only after inspecting the final PDF.",
            "",
        ]
    )
    for row in rows:
        saved = existing.get(row["key"], {})
        lines.extend(
            [
                f"### `{row['key']}`",
                "",
                f"- Check label: {row['label']}",
                f"- Required check: {row['required_check']}",
                f"- Automated evidence state: `{row['automated_evidence_state']}`",
                f"- Evidence: {row['evidence']}",
                "- Final rendered-PDF decision:",
                "",
                *code_block(saved.get("decision", "")),
                "",
                "- Reviewer and review date:",
                "",
                *code_block(saved.get("reviewer", "")),
                "",
                "- Opened final PDF checked:",
                "",
                *code_block(saved.get("opened_pdf", "")),
                "",
                "- Corrections or recompilation notes:",
                "",
                *code_block(saved.get("corrections", "")),
                "",
            ]
        )

    lines.extend(
        [
            "## Completion Rule",
            "",
            "- Every row must be marked `APPROVED_NO_CHANGES` or `APPROVED_AFTER_CORRECTION`.",
            "- Every approved row must include reviewer/date and `YES` for opened final PDF checked.",
            "- Rows marked `APPROVED_AFTER_CORRECTION` must describe the completed correction and recompile/reinspection.",
            "- Rows marked `NEEDS_CORRECTION_OR_RECOMPILE` or `BLOCKED_BY_METADATA_OR_OTHER_SIGNOFF` block real submission.",
            "- This form must be regenerated after metadata application, reference edits, figure regeneration, PDF recompilation, or clinical overlay signoff changes.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    existing = parse_existing_form()
    rows = build_rows(existing)
    write_csv(rows)
    write_markdown(rows, existing)
    blocking_rows = [row for row in rows if row["signoff_status"] != "APPROVED"]
    approved_rows = [row for row in rows if row["signoff_status"] == "APPROVED"]
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Rendered PDF author signoff: approved={len(approved_rows)}; blocking={len(blocking_rows)}")


if __name__ == "__main__":
    main()
