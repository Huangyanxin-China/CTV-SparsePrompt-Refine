#!/usr/bin/env python3
"""Create a signoff form for final publisher-record reference review."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
PACKET_CSV = ROOT / "reports" / "vsi_reference_publisher_verification_packet_20260531.csv"
MD_OUT = PKG / "reference_publisher_signoff_form.md"
CSV_OUT = ROOT / "reports" / "vsi_reference_publisher_signoff_20260531.csv"

APPROVED_DECISIONS = {"APPROVED_NO_CHANGES", "APPROVED_AFTER_BIBTEX_UPDATE"}
OPEN_DECISIONS = {"", "NEEDS_BIBTEX_UPDATE", "REJECTED_OR_REPLACE_REFERENCE"}
ALLOWED_DECISIONS = APPROVED_DECISIONS | OPEN_DECISIONS


def load_packet_rows() -> list[dict[str, str]]:
    if not PACKET_CSV.exists():
        return []
    with PACKET_CSV.open(newline="") as handle:
        return list(csv.DictReader(handle))


def parse_existing_form() -> dict[str, dict[str, str]]:
    if not MD_OUT.exists():
        return {}
    text = MD_OUT.read_text()
    existing: dict[str, dict[str, str]] = {}
    section_pattern = re.compile(r"^### `([^`]+)`\n(.*?)(?=^### `|^## |\Z)", re.M | re.S)
    field_patterns = {
        "decision": re.compile(r"- Approved final decision:\n\n```text\n(.*?)\n```", re.S),
        "reviewer": re.compile(r"- Reviewer and review date:\n\n```text\n(.*?)\n```", re.S),
        "corrections": re.compile(r"- Corrections applied to `references\.bib`:\n\n```text\n(.*?)\n```", re.S),
        "source": re.compile(r"- Source checked:\n\n```text\n(.*?)\n```", re.S),
    }
    for match in section_pattern.finditer(text):
        key = match.group(1)
        body = match.group(2)
        existing[key] = {}
        for name, pattern in field_patterns.items():
            value_match = pattern.search(body)
            existing[key][name] = value_match.group(1).strip() if value_match else ""
    return existing


def decision_status(decision: str, reviewer: str, source: str, corrections: str) -> tuple[str, str]:
    normalized = decision.strip()
    if normalized not in ALLOWED_DECISIONS:
        return "BLOCKER_INVALID_DECISION", "Use APPROVED_NO_CHANGES, APPROVED_AFTER_BIBTEX_UPDATE, NEEDS_BIBTEX_UPDATE, or REJECTED_OR_REPLACE_REFERENCE."
    if normalized in APPROVED_DECISIONS:
        if not reviewer:
            return "BLOCKER_REVIEWER_MISSING", "Record reviewer name/initials and review date."
        if not source:
            return "BLOCKER_SOURCE_MISSING", "Record the authoritative publisher, DOI, PubMed, arXiv, or proceedings source checked."
        if normalized == "APPROVED_AFTER_BIBTEX_UPDATE" and not corrections:
            return "BLOCKER_CORRECTION_NOTE_MISSING", "Describe the BibTeX correction that was applied."
        return "APPROVED", "No further reference-review action for this row."
    if normalized == "NEEDS_BIBTEX_UPDATE":
        return "BLOCKER_NEEDS_BIBTEX_UPDATE", "Update references.bib, regenerate audits, then re-review this row."
    if normalized == "REJECTED_OR_REPLACE_REFERENCE":
        return "BLOCKER_REFERENCE_REPLACEMENT_REQUIRED", "Replace or remove this reference and regenerate the manuscript/audits."
    return "BLOCKER_REVIEW_REQUIRED", "Verify this row against an authoritative publisher, DOI, PubMed, arXiv, or proceedings record."


def build_rows(packet_rows: list[dict[str, str]], existing: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for packet in packet_rows:
        key = packet.get("key", "")
        saved = existing.get(key, {})
        decision = saved.get("decision", "").strip()
        reviewer = saved.get("reviewer", "").strip()
        corrections = saved.get("corrections", "").strip()
        source = saved.get("source", "").strip()
        status, action = decision_status(decision, reviewer, source, corrections)
        rows.append(
            {
                "key": key,
                "type": packet.get("type", ""),
                "year": packet.get("year", ""),
                "title": packet.get("title", ""),
                "venue": packet.get("venue", ""),
                "source_id": packet.get("source_id", ""),
                "resolver": packet.get("resolver", ""),
                "manual_review_status": packet.get("manual_review_status", ""),
                "required_checks": packet.get("required_checks", ""),
                "final_decision": decision,
                "reviewer_and_date_present": "YES" if reviewer else "NO",
                "source_checked_present": "YES" if source else "NO",
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
        "type",
        "year",
        "title",
        "venue",
        "source_id",
        "resolver",
        "manual_review_status",
        "required_checks",
        "final_decision",
        "reviewer_and_date_present",
        "source_checked_present",
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
    status = "REFERENCE_PUBLISHER_SIGNOFF_COMPLETE" if not blocking_rows and rows else "REFERENCE_PUBLISHER_SIGNOFF_REQUIRED"

    lines = [
        "# Reference Publisher Signoff Form",
        "",
        "This form records final human verification of every BibTeX entry against authoritative publisher, DOI, PubMed, arXiv, proceedings, or open-access records. It preserves previously entered signoff values when regenerated.",
        "",
        "## Summary",
        "",
        f"- Signoff status: {status}",
        f"- Entries requiring signoff: {len(rows)}",
        f"- Entries approved: {len(approved_rows)}",
        f"- Blocking signoff rows: {len(blocking_rows)}",
        "- Source queue: `reference_publisher_verification_packet.md`",
        "- Machine-readable signoff audit: `reports/vsi_reference_publisher_signoff_20260531.csv`",
        "- Allowed final decisions: `APPROVED_NO_CHANGES`, `APPROVED_AFTER_BIBTEX_UPDATE`, `NEEDS_BIBTEX_UPDATE`, `REJECTED_OR_REPLACE_REFERENCE`",
        "- Regeneration command: `make -C manuscript_vsi_biomedical_data ref-signoff`",
        "",
        "## Signoff Status Table",
        "",
        "| Key | Packet status | Final decision | Signoff status | Required action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{md_escape(row['key'])}`",
                    f"`{md_escape(row['manual_review_status'])}`",
                    f"`{md_escape(row['final_decision'] or 'BLANK')}`",
                    f"`{md_escape(row['signoff_status'])}`",
                    md_escape(row["required_action"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Per-Reference Human Signoff",
            "",
            "For each entry, fill the final decision, reviewer/date, source checked, and correction note if applicable. Do not mark a row approved until `references.bib` reflects any required corrections and the relevant audits have been regenerated.",
            "",
        ]
    )
    for row in rows:
        saved = existing.get(row["key"], {})
        lines.extend(
            [
                f"### `{row['key']}`",
                "",
                f"- Title: {row['title']}",
                f"- Venue/year: {row['venue']} ({row['year']})",
                f"- Source ID: `{row['source_id'] or '--'}`",
                f"- Resolver: {row['resolver'] or '--'}",
                f"- Current packet status: `{row['manual_review_status']}`",
                f"- Required checks: {row['required_checks']}",
                "- Approved final decision:",
                "",
                *code_block(saved.get("decision", "")),
                "",
                "- Reviewer and review date:",
                "",
                *code_block(saved.get("reviewer", "")),
                "",
                "- Source checked:",
                "",
                *code_block(saved.get("source", "")),
                "",
                "- Corrections applied to `references.bib`:",
                "",
                *code_block(saved.get("corrections", "")),
                "",
            ]
        )

    lines.extend(
        [
            "## Completion Rule",
            "",
            "- Every row must be marked `APPROVED_NO_CHANGES` or `APPROVED_AFTER_BIBTEX_UPDATE` with reviewer/date and source checked.",
            "- Rows marked `NEEDS_BIBTEX_UPDATE` or `REJECTED_OR_REPLACE_REFERENCE` block submission until `references.bib` and manuscript citations are updated.",
            "- This form is human signoff evidence; it does not replace the structural, identifier, or online metadata audits.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    packet_rows = load_packet_rows()
    existing = parse_existing_form()
    rows = build_rows(packet_rows, existing)
    write_csv(rows)
    write_markdown(rows, existing)
    blocking_rows = [row for row in rows if row["signoff_status"] != "APPROVED"]
    approved_rows = [row for row in rows if row["signoff_status"] == "APPROVED"]
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Reference publisher signoff: approved={len(approved_rows)}; blocking={len(blocking_rows)}")


if __name__ == "__main__":
    main()
