#!/usr/bin/env python3
"""Create a preserved signoff form for final author declarations."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "author_declaration_signoff_form.md"
CSV_OUT = ROOT / "reports" / "vsi_author_declaration_signoff_20260601.csv"

APPROVED_DECISIONS = {"APPROVED_CONFIRMED", "APPROVED_AFTER_UPDATE"}
OPEN_DECISIONS = {"", "NEEDS_METADATA_UPDATE", "NEEDS_DECLARATION_UPDATE", "NEEDS_AUTHOR_CONFIRMATION"}
ALLOWED_DECISIONS = APPROVED_DECISIONS | OPEN_DECISIONS
YES_VALUES = {"YES", "Y", "TRUE", "CHECKED"}


CHECKS = [
    {
        "key": "final_author_list_order",
        "label": "Final author list and order",
        "required_check": "Confirm all author names, ordering, and manuscript title-page names are final.",
        "evidence_needles": [
            ("submission_metadata_author_fill_form.md", "Required fields still blocked:"),
            ("submission_metadata_lock_audit.md", "Status: NOT_READY_FOR_METADATA_LOCK"),
            ("main.tex", "Institution to be finalized"),
        ],
    },
    {
        "key": "affiliations_contact_details",
        "label": "Affiliations and contact details",
        "required_check": "Confirm affiliations, institution names, city/country, corresponding email, and postal address.",
        "evidence_needles": [
            ("submission_metadata_template.yaml", "organization: TODO_REPLACE"),
            ("submission_metadata_template.yaml", "email: TODO_REPLACE"),
            ("cover_letter.txt", "Corresponding author details to be finalized"),
        ],
    },
    {
        "key": "corresponding_author_authority",
        "label": "Corresponding-author authority",
        "required_check": "Confirm the corresponding/submitting author is authorized to submit on behalf of all authors.",
        "evidence_needles": [
            ("official_requirements_snapshot.md", "AUTHOR_APPROVAL"),
            ("author_submission_info_needed.md", "Corresponding author"),
        ],
    },
    {
        "key": "credit_roles",
        "label": "CRediT roles",
        "required_check": "Confirm author-approved CRediT roles for every author and contribution category.",
        "evidence_needles": [
            ("credit_author_statement.txt", "CRediT"),
            ("submission_metadata_template.yaml", "conceptualization: TODO_REPLACE"),
            ("submission_blocker_audit.md", "BLOCKER_CREDIT_AUTHORSHIP"),
        ],
    },
    {
        "key": "all_authors_final_manuscript_approval",
        "label": "All-author final manuscript approval",
        "required_check": "Confirm every author approved the exact manuscript version intended for submission.",
        "evidence_needles": [
            ("official_requirements_snapshot.md", "AUTHOR_APPROVAL"),
            ("submission_blocker_audit.md", "final author approval"),
            ("final_submission_handoff.md", "author approval"),
        ],
    },
    {
        "key": "responsible_authority_institutional_approval",
        "label": "Responsible-authority approval",
        "required_check": "Confirm responsible institutional or study authorities approve the submission where required.",
        "evidence_needles": [
            ("official_requirements_snapshot.md", "responsible authorities"),
            ("submission_metadata_completion_packet.md", "ethics"),
            ("author_submission_info_needed.md", "ethics"),
        ],
    },
    {
        "key": "competing_interest_declaration",
        "label": "Competing-interest declaration",
        "required_check": "Confirm all authors reviewed and approved the declaration of competing interests.",
        "evidence_needles": [
            ("declaration_of_interest.txt", "Declaration of Competing Interest"),
            ("main.tex", "Declaration of Competing Interest"),
            ("official_requirements_snapshot.md", "COMPETING_INTERESTS"),
        ],
    },
    {
        "key": "data_availability_statement",
        "label": "Data availability statement",
        "required_check": "Confirm the private-data limitation, shareable aggregate outputs, and approval wording are final.",
        "evidence_needles": [
            ("data_availability_statement.txt", "Data Availability"),
            ("external_validity_public_data_audit.md", "Private institutional cohort disclosed"),
            ("official_requirements_snapshot.md", "RESEARCH_DATA_STATEMENT"),
        ],
    },
    {
        "key": "generative_ai_declaration",
        "label": "Generative-AI declaration",
        "required_check": "Confirm the declared use of AI assistance in manuscript preparation is accurate and author-approved.",
        "evidence_needles": [
            ("generative_ai_statement.txt", "Generative AI"),
            ("main.tex", "Generative AI"),
            ("official_requirements_snapshot.md", "GENAI_DECLARATION"),
        ],
    },
    {
        "key": "ethics_consent_deidentification",
        "label": "Ethics, consent, and deidentification",
        "required_check": "Confirm IRB/ethics body, approval or exemption number, consent/waiver wording, and deidentification language.",
        "evidence_needles": [
            ("submission_metadata_author_fill_form.md", "ethics.approval_body"),
            ("submission_metadata_template.yaml", "approval_body: TODO_REPLACE"),
            ("main.tex", "must be inserted before submission"),
        ],
    },
    {
        "key": "funding_acknowledgements",
        "label": "Funding and acknowledgements",
        "required_check": "Confirm grant numbers, sponsor role, acknowledgements, or no-specific-funding wording.",
        "evidence_needles": [
            ("submission_metadata_author_fill_form.md", "funding.statement"),
            ("submission_metadata_template.yaml", "statement: TODO_REPLACE"),
            ("main.tex", "funding information should be finalized"),
        ],
    },
    {
        "key": "originality_exclusive_submission_permissions",
        "label": "Originality, exclusive submission, and permissions",
        "required_check": "Confirm originality, exclusive submission, required permissions, and APC/license awareness.",
        "evidence_needles": [
            ("submission_checklist.md", "Submission checklist"),
            ("official_requirements_snapshot.md", "SUBMISSION_CHECKLIST"),
            ("final_submission_handoff.md", "Editorial Manager upload"),
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
        "decision": re.compile(r"- Final declaration decision:\n\n```text\n(.*?)\n```", re.S),
        "confirming_party": re.compile(r"- Confirming party and date:\n\n```text\n(.*?)\n```", re.S),
        "all_covered": re.compile(r"- All required authors/authorities covered:\n\n```text\n(.*?)\n```", re.S),
        "source_checked": re.compile(r"- Source or approval record checked:\n\n```text\n(.*?)\n```", re.S),
        "notes": re.compile(r"- Corrections or notes:\n\n```text\n(.*?)\n```", re.S),
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
    confirming_party: str,
    all_covered: str,
    source_checked: str,
    notes: str,
) -> tuple[str, str]:
    normalized = decision.strip()
    if normalized not in ALLOWED_DECISIONS:
        return (
            "BLOCKER_INVALID_DECISION",
            "Use APPROVED_CONFIRMED, APPROVED_AFTER_UPDATE, NEEDS_METADATA_UPDATE, NEEDS_DECLARATION_UPDATE, or NEEDS_AUTHOR_CONFIRMATION.",
        )
    if normalized in APPROVED_DECISIONS:
        if not confirming_party.strip():
            return "BLOCKER_CONFIRMING_PARTY_MISSING", "Record confirming party name/role and confirmation date."
        if not checked(all_covered):
            return "BLOCKER_AUTHOR_OR_AUTHORITY_COVERAGE_MISSING", "Record YES only after all required authors or authorities are covered."
        if not source_checked.strip():
            return "BLOCKER_APPROVAL_RECORD_MISSING", "Record the source approval record, email thread, institutional system entry, or equivalent evidence checked."
        if normalized == "APPROVED_AFTER_UPDATE" and not notes.strip():
            return "BLOCKER_UPDATE_NOTE_MISSING", "Describe the metadata or declaration update that was completed before approval."
        return "APPROVED", "No further author/declaration action for this row."
    if normalized == "NEEDS_METADATA_UPDATE":
        return "BLOCKER_NEEDS_METADATA_UPDATE", "Update author, affiliation, ethics, funding, or CRediT metadata, then re-review this row."
    if normalized == "NEEDS_DECLARATION_UPDATE":
        return "BLOCKER_NEEDS_DECLARATION_UPDATE", "Update the relevant declaration text, then re-review this row."
    if normalized == "NEEDS_AUTHOR_CONFIRMATION":
        return "BLOCKER_NEEDS_AUTHOR_CONFIRMATION", "Obtain author or responsible-authority confirmation, then record it here."
    return "BLOCKER_AUTHOR_DECLARATION_REVIEW_REQUIRED", "Record an approved final declaration decision and supporting confirmation evidence."


def build_rows(existing: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in CHECKS:
        key = item["key"]
        saved = existing.get(key, {})
        decision = saved.get("decision", "").strip()
        confirming_party = saved.get("confirming_party", "").strip()
        all_covered = saved.get("all_covered", "").strip()
        source_checked = saved.get("source_checked", "").strip()
        notes = saved.get("notes", "").strip()
        status, action = decision_status(decision, confirming_party, all_covered, source_checked, notes)
        evidence = "; ".join(
            f"{rel}: {first_evidence_line(rel, needle)}" for rel, needle in item["evidence_needles"]
        )
        rows.append(
            {
                "key": key,
                "label": item["label"],
                "required_check": item["required_check"],
                "evidence": evidence,
                "final_decision": decision,
                "confirming_party_and_date_present": "YES" if confirming_party else "NO",
                "all_required_authors_or_authorities_covered": "YES" if checked(all_covered) else "NO",
                "source_or_approval_record_checked_present": "YES" if source_checked else "NO",
                "corrections_or_notes_present": "YES" if notes else "NO",
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
        "evidence",
        "final_decision",
        "confirming_party_and_date_present",
        "all_required_authors_or_authorities_covered",
        "source_or_approval_record_checked_present",
        "corrections_or_notes_present",
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
    status = "AUTHOR_DECLARATION_SIGNOFF_COMPLETE" if rows and not blocking_rows else "AUTHOR_DECLARATION_SIGNOFF_REQUIRED"

    lines = [
        "# Author Declaration Signoff Form",
        "",
        "This form records final author and responsible-authority approval for submission-critical declarations. It preserves previously entered values when regenerated and does not replace institutional records, author email approvals, or Editorial Manager declarations.",
        "",
        "## Summary",
        "",
        f"- Signoff status: {status}",
        f"- Declaration signoff checklist rows: {len(rows)}",
        f"- Approved declaration signoff rows: {len(approved_rows)}",
        f"- Blocking signoff rows: {len(blocking_rows)}",
        "- Source metadata form: `submission_metadata_author_fill_form.md`",
        "- Source metadata template: `submission_metadata_template.yaml`",
        "- Related declaration files: `declaration_of_interest.txt`, `data_availability_statement.txt`, `generative_ai_statement.txt`, `credit_author_statement.txt`",
        "- Machine-readable signoff audit: `reports/vsi_author_declaration_signoff_20260601.csv`",
        "- Allowed final decisions: `APPROVED_CONFIRMED`, `APPROVED_AFTER_UPDATE`, `NEEDS_METADATA_UPDATE`, `NEEDS_DECLARATION_UPDATE`, `NEEDS_AUTHOR_CONFIRMATION`",
        "- Regeneration command: `make -C manuscript_vsi_biomedical_data author-signoff`",
        "",
        "## Signoff Status Table",
        "",
        "| Row | Required check | Final decision | Covered | Source checked | Signoff status | Required action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{md_escape(row['key'])}`",
                    md_escape(row["label"]),
                    f"`{md_escape(row['final_decision'] or 'BLANK')}`",
                    f"`{md_escape(row['all_required_authors_or_authorities_covered'])}`",
                    f"`{md_escape(row['source_or_approval_record_checked_present'])}`",
                    f"`{md_escape(row['signoff_status'])}`",
                    md_escape(row["required_action"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Per-Declaration Human Signoff",
            "",
            "For each row, confirm the final author-approved source after metadata and declaration edits. Use `YES` for the coverage field only after all required authors or responsible authorities are covered.",
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
                f"- Evidence: {row['evidence']}",
                "- Final declaration decision:",
                "",
                *code_block(saved.get("decision", "")),
                "",
                "- Confirming party and date:",
                "",
                *code_block(saved.get("confirming_party", "")),
                "",
                "- All required authors/authorities covered:",
                "",
                *code_block(saved.get("all_covered", "")),
                "",
                "- Source or approval record checked:",
                "",
                *code_block(saved.get("source_checked", "")),
                "",
                "- Corrections or notes:",
                "",
                *code_block(saved.get("notes", "")),
                "",
            ]
        )

    lines.extend(
        [
            "## Completion Rule",
            "",
            "- Every row must be marked `APPROVED_CONFIRMED` or `APPROVED_AFTER_UPDATE`.",
            "- Every approved row must include confirming party/date, `YES` for all required authors/authorities covered, and the source approval record checked.",
            "- Rows marked `APPROVED_AFTER_UPDATE` must describe the completed metadata or declaration update.",
            "- Rows marked `NEEDS_METADATA_UPDATE`, `NEEDS_DECLARATION_UPDATE`, or `NEEDS_AUTHOR_CONFIRMATION` block real submission.",
            "- This form must be regenerated after metadata application, declaration edits, author-list changes, funding/ethics changes, or final PDF signoff changes.",
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
    print(f"Author declaration signoff: approved={len(approved_rows)}; blocking={len(blocking_rows)}")


if __name__ == "__main__":
    main()
