#!/usr/bin/env python3
"""Create a preserved human signoff form for clinical overlay pixel review."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
PACKET_CSV = ROOT / "reports" / "vsi_clinical_overlay_visual_review_packet_20260531.csv"
MD_OUT = PKG / "clinical_overlay_signoff_form.md"
CSV_OUT = ROOT / "reports" / "vsi_clinical_overlay_signoff_20260531.csv"

APPROVED_DECISIONS = {"APPROVED_NO_VISIBLE_PHI", "APPROVED_AFTER_REDACTION"}
OPEN_DECISIONS = {"", "NEEDS_REDACTION_OR_REGENERATION", "REPLACE_OR_REMOVE_FIGURE"}
ALLOWED_DECISIONS = APPROVED_DECISIONS | OPEN_DECISIONS
YES_VALUES = {"YES", "Y", "TRUE", "CHECKED"}


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
        "decision": re.compile(r"- Final pixel-review decision:\n\n```text\n(.*?)\n```", re.S),
        "reviewer": re.compile(r"- Reviewer and review date:\n\n```text\n(.*?)\n```", re.S),
        "full_png": re.compile(r"- Full-resolution PNG checked:\n\n```text\n(.*?)\n```", re.S),
        "rendered_pdf": re.compile(r"- Rendered PDF checked:\n\n```text\n(.*?)\n```", re.S),
        "corrections": re.compile(r"- Corrections or regeneration notes:\n\n```text\n(.*?)\n```", re.S),
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


def decision_status(
    decision: str,
    reviewer: str,
    full_png: str,
    rendered_pdf: str,
    corrections: str,
) -> tuple[str, str]:
    normalized = decision.strip()
    if normalized not in ALLOWED_DECISIONS:
        return (
            "BLOCKER_INVALID_DECISION",
            "Use APPROVED_NO_VISIBLE_PHI, APPROVED_AFTER_REDACTION, NEEDS_REDACTION_OR_REGENERATION, or REPLACE_OR_REMOVE_FIGURE.",
        )
    if normalized in APPROVED_DECISIONS:
        if not reviewer.strip():
            return "BLOCKER_REVIEWER_MISSING", "Record reviewer name/initials and review date."
        if not checked(full_png):
            return "BLOCKER_FULL_RESOLUTION_PNG_NOT_CHECKED", "Record YES after inspecting the full-resolution PNG."
        if not checked(rendered_pdf):
            return "BLOCKER_RENDERED_PDF_NOT_CHECKED", "Record YES after inspecting the rendered PDF placement."
        if normalized == "APPROVED_AFTER_REDACTION" and not corrections.strip():
            return "BLOCKER_REDACTION_NOTE_MISSING", "Describe the redaction, regeneration, or replacement that was completed."
        return "APPROVED", "No further clinical overlay pixel-review action for this row."
    if normalized == "NEEDS_REDACTION_OR_REGENERATION":
        return "BLOCKER_NEEDS_REDACTION_OR_REGENERATION", "Regenerate or redact the figure, then rerun the figure, PDF, and release audits."
    if normalized == "REPLACE_OR_REMOVE_FIGURE":
        return "BLOCKER_REPLACE_OR_REMOVE_FIGURE", "Replace or remove this figure and rerun manuscript figure, PDF, and release audits."
    return "BLOCKER_PIXEL_REVIEW_REQUIRED", "Inspect the full-resolution PNG and rendered PDF, then record an approved final decision."


def build_rows(packet_rows: list[dict[str, str]], existing: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for packet in packet_rows:
        key = packet.get("path", "")
        saved = existing.get(key, {})
        decision = saved.get("decision", "").strip()
        reviewer = saved.get("reviewer", "").strip()
        full_png = saved.get("full_png", "").strip()
        rendered_pdf = saved.get("rendered_pdf", "").strip()
        corrections = saved.get("corrections", "").strip()
        status, action = decision_status(decision, reviewer, full_png, rendered_pdf, corrections)
        rows.append(
            {
                "path": key,
                "role": packet.get("role", ""),
                "width": packet.get("width", ""),
                "height": packet.get("height", ""),
                "sha256_prefix": packet.get("sha256_prefix", ""),
                "packet_manual_visual_status": packet.get("manual_visual_status", ""),
                "packet_clinical_owner_signoff_status": packet.get("clinical_owner_signoff_status", ""),
                "final_decision": decision,
                "reviewer_and_date_present": "YES" if reviewer else "NO",
                "full_resolution_png_checked": "YES" if checked(full_png) else "NO",
                "rendered_pdf_checked": "YES" if checked(rendered_pdf) else "NO",
                "correction_note_present": "YES" if corrections else "NO",
                "signoff_status": status,
                "required_action": action,
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "path",
        "role",
        "width",
        "height",
        "sha256_prefix",
        "packet_manual_visual_status",
        "packet_clinical_owner_signoff_status",
        "final_decision",
        "reviewer_and_date_present",
        "full_resolution_png_checked",
        "rendered_pdf_checked",
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
    status = "CLINICAL_OVERLAY_SIGNOFF_COMPLETE" if rows and not blocking_rows else "CLINICAL_OVERLAY_SIGNOFF_REQUIRED"

    lines = [
        "# Clinical Overlay Signoff Form",
        "",
        "This form records final human pixel-review signoff for clinical overlay figures. It preserves previously entered values when regenerated and is the required closure record after the visual-review queue and AI visual prescreen.",
        "",
        "## Summary",
        "",
        f"- Signoff status: {status}",
        f"- Clinical overlay files requiring signoff: {len(rows)}",
        f"- Approved overlay files: {len(approved_rows)}",
        f"- Blocking signoff rows: {len(blocking_rows)}",
        "- Source queue: `clinical_overlay_visual_review_packet.md`",
        "- AI prescreen companion: `clinical_overlay_ai_visual_prescreen.md`",
        "- Machine-readable signoff audit: `reports/vsi_clinical_overlay_signoff_20260531.csv`",
        "- Allowed final decisions: `APPROVED_NO_VISIBLE_PHI`, `APPROVED_AFTER_REDACTION`, `NEEDS_REDACTION_OR_REGENERATION`, `REPLACE_OR_REMOVE_FIGURE`",
        "- Regeneration command: `make -C manuscript_vsi_biomedical_data overlay-signoff`",
        "",
        "## Signoff Status Table",
        "",
        "| File | Packet signoff status | Final decision | Full PNG checked | Rendered PDF checked | Signoff status | Required action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{md_escape(row['path'])}`",
                    f"`{md_escape(row['packet_clinical_owner_signoff_status'])}`",
                    f"`{md_escape(row['final_decision'] or 'BLANK')}`",
                    f"`{md_escape(row['full_resolution_png_checked'])}`",
                    f"`{md_escape(row['rendered_pdf_checked'])}`",
                    f"`{md_escape(row['signoff_status'])}`",
                    md_escape(row["required_action"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Per-Figure Human Signoff",
            "",
            "For each row, inspect the full-resolution PNG and its rendered PDF placement. Use `YES` for the two checked fields only after inspection is complete.",
            "",
        ]
    )
    for row in rows:
        saved = existing.get(row["path"], {})
        dims = f"{row['width']}x{row['height']}" if row["width"] and row["height"] else "--"
        lines.extend(
            [
                f"### `{row['path']}`",
                "",
                f"- Role: {row['role']}",
                f"- Dimensions: {dims}",
                f"- SHA256 prefix: `{row['sha256_prefix'] or '--'}`",
                f"- Source queue manual status: `{row['packet_manual_visual_status']}`",
                f"- Source queue clinical-owner signoff status: `{row['packet_clinical_owner_signoff_status']}`",
                "- Final pixel-review decision:",
                "",
                *code_block(saved.get("decision", "")),
                "",
                "- Reviewer and review date:",
                "",
                *code_block(saved.get("reviewer", "")),
                "",
                "- Full-resolution PNG checked:",
                "",
                *code_block(saved.get("full_png", "")),
                "",
                "- Rendered PDF checked:",
                "",
                *code_block(saved.get("rendered_pdf", "")),
                "",
                "- Corrections or regeneration notes:",
                "",
                *code_block(saved.get("corrections", "")),
                "",
            ]
        )

    lines.extend(
        [
            "## Completion Rule",
            "",
            "- Every row must be marked `APPROVED_NO_VISIBLE_PHI` or `APPROVED_AFTER_REDACTION`.",
            "- Every approved row must include reviewer/date, `YES` for full-resolution PNG review, and `YES` for rendered PDF review.",
            "- Rows marked `APPROVED_AFTER_REDACTION` must describe the completed redaction, regeneration, or replacement.",
            "- Rows marked `NEEDS_REDACTION_OR_REGENERATION` or `REPLACE_OR_REMOVE_FIGURE` block submission until figures, PDF, and release audits are regenerated.",
            "- This form is human signoff evidence; it does not replace the generated visual-review packet, AI visual prescreen, or final submitting-author PDF signoff.",
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
    print(f"Clinical overlay signoff: approved={len(approved_rows)}; blocking={len(blocking_rows)}")


if __name__ == "__main__":
    main()
