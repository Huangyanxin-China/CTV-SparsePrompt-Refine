#!/usr/bin/env python3
"""Create an author-facing packet for completing VSI submission metadata."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
METADATA = PKG / "submission_metadata_template.yaml"
MD_OUT = PKG / "submission_metadata_completion_packet.md"
CSV_OUT = ROOT / "reports" / "vsi_submission_metadata_completion_packet_20260531.csv"
FORM_OUT = PKG / "submission_metadata_author_fill_form.md"

PLACEHOLDERS = [
    "TODO_REPLACE",
    "TODO_REPLACE_OR_LEAVE_EMPTY",
    "to be finalized",
    "Institution to be finalized",
    "corresponding.email",
]


@dataclass(frozen=True)
class MetadataField:
    path: str
    label: str
    required: bool
    destination: str
    guidance: str


FIELDS = [
    MetadataField("authors.0.name", "First author name", True, "main.tex; Editorial Manager author list", "Confirm spelling and order."),
    MetadataField("authors.0.email", "First author email", True, "submission system; metadata consistency", "Use a valid institutional or approved contact email."),
    MetadataField("authors.0.orcid", "First author ORCID", False, "Editorial Manager author metadata", "Use a valid ORCID if available; otherwise leave blank."),
    MetadataField("affiliations.0.organization", "Affiliation organization", True, "main.tex affiliation block; submission system", "Use the official institution name."),
    MetadataField("affiliations.0.city", "Affiliation city", True, "main.tex affiliation block; submission system", "Use the institution city."),
    MetadataField("affiliations.0.country", "Affiliation country", True, "main.tex affiliation block; submission system", "Use the institution country."),
    MetadataField("corresponding_author.name", "Corresponding author name", True, "main.tex; cover_letter.txt; submission system", "Must match the final corresponding author."),
    MetadataField("corresponding_author.email", "Corresponding author email", True, "main.tex; cover_letter.txt; submission system", "Use the email for Editorial Manager correspondence."),
    MetadataField("corresponding_author.address", "Corresponding author address", True, "cover_letter.txt; submission system", "Use the full postal or institutional contact address required by the journal."),
    MetadataField("ethics.approval_body", "Ethics approval body", True, "main.tex ethics statement; submission system", "Use the exact IRB/ethics committee or exemption authority name."),
    MetadataField("ethics.approval_number", "Ethics approval number or exemption", True, "main.tex ethics statement; submission system", "Use the approval identifier or official exemption language."),
    MetadataField("ethics.consent_or_waiver", "Consent or waiver language", True, "main.tex ethics statement; submission system", "Use institutionally approved retrospective de-identified-data consent language."),
    MetadataField("ethics.deidentification_statement", "De-identification statement", True, "main.tex ethics/data governance language", "Confirm that it matches institutional data-governance constraints."),
    MetadataField("funding.statement", "Funding statement", True, "main.tex acknowledgements/funding; submission system", "List funders and grant numbers, or state no specific funding."),
    MetadataField("funding.grant_numbers", "Grant numbers", False, "submission system funding metadata", "List grant numbers if applicable."),
    MetadataField("author_contributions.conceptualization", "CRediT: Conceptualization", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
    MetadataField("author_contributions.methodology", "CRediT: Methodology", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
    MetadataField("author_contributions.software", "CRediT: Software", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
    MetadataField("author_contributions.validation", "CRediT: Validation", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
    MetadataField("author_contributions.investigation", "CRediT: Investigation", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
    MetadataField("author_contributions.writing_original_draft", "CRediT: Writing - original draft", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
    MetadataField("author_contributions.writing_review_editing", "CRediT: Writing - review and editing", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
    MetadataField("author_contributions.supervision", "CRediT: Supervision", True, "credit_author_statement.txt; main.tex", "Use author initials or names approved by all authors."),
]


def load_metadata() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(METADATA.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def get_path(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value).strip()


def has_placeholder(value: Any) -> bool:
    text = value_text(value)
    if not text:
        return True
    return any(marker in text for marker in PLACEHOLDERS)


def valid_email(value: Any) -> bool:
    text = value_text(value)
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))


def field_status(field: MetadataField, value: Any) -> str:
    if not field.required:
        return "OPTIONAL_EMPTY" if has_placeholder(value) else "OPTIONAL_FILLED"
    if has_placeholder(value):
        return "BLOCKER"
    if field.path.endswith(".email") and not valid_email(value):
        return "BLOCKER"
    return "READY"


def rows(data: dict[str, Any]) -> list[dict[str, str]]:
    output = []
    for field in FIELDS:
        value = get_path(data, field.path)
        status = field_status(field, value)
        current = value_text(value) or "<empty>"
        output.append(
            {
                "field": field.path,
                "label": field.label,
                "required": "yes" if field.required else "no",
                "status": status,
                "current_value": current,
                "destination": field.destination,
                "guidance": field.guidance,
            }
        )
    return output


def write_csv(output: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["field", "label", "required", "status", "current_value", "destination", "guidance"],
        )
        writer.writeheader()
        writer.writerows(output)


def write_markdown(output: list[dict[str, str]]) -> None:
    required_blockers = [row for row in output if row["required"] == "yes" and row["status"] == "BLOCKER"]
    optional_open = [row for row in output if row["status"] == "OPTIONAL_EMPTY"]
    status = "BLOCKED_BY_REQUIRED_METADATA" if required_blockers else "READY_FOR_AUTHOR_REVIEW"

    lines = [
        "# Submission Metadata Completion Packet",
        "",
        "This packet converts the YAML metadata template into an author-facing completion checklist. It does not invent institutional, ethics, funding, or authorship information.",
        "",
        "## Summary",
        "",
        f"- Packet status: {status}",
        f"- Required metadata blockers: {len(required_blockers)}",
        f"- Optional open fields: {len(optional_open)}",
        "- Source metadata file: `submission_metadata_template.yaml`",
        "- Human fill form: `submission_metadata_author_fill_form.md`",
        "- Fill-form sync dry-run command: `make -C manuscript_vsi_biomedical_data metadata-fill-sync`",
        "- Author-approved YAML sync command: `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply`",
        "- Dry-run validation command: `make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan`",
        "- Author-approved apply command: `python scripts/apply_vsi_submission_metadata.py --apply`",
        "- Final release command: `make -C manuscript_vsi_biomedical_data release`",
        "",
        "## Required Metadata Fields",
        "",
        "| Field | Label | Status | Current value | Destination | Guidance |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in output:
        if row["required"] != "yes":
            continue
        cells = [
            f"`{row['field']}`",
            row["label"],
            row["status"],
            f"`{row['current_value']}`",
            row["destination"],
            row["guidance"],
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## Optional Metadata Fields",
            "",
            "| Field | Label | Status | Current value | Destination | Guidance |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in output:
        if row["required"] == "yes":
            continue
        cells = [
            f"`{row['field']}`",
            row["label"],
            row["status"],
            f"`{row['current_value']}`",
            row["destination"],
            row["guidance"],
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## Completion Procedure",
            "",
            "1. Use `submission_metadata_author_fill_form.md` to collect institutionally approved final text for every `BLOCKER` field.",
            "2. Run `make -C manuscript_vsi_biomedical_data metadata-fill-sync` to verify whether the fill form can be synchronized into YAML.",
            "3. After approval, run `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply` or manually replace every `BLOCKER` value in `submission_metadata_template.yaml` with the approved final text.",
            "4. Leave optional fields empty only when the corresponding author confirms that the information is unavailable or not required.",
            "5. Run `make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan` and require zero required metadata blockers.",
            "6. After final author approval, run `python scripts/apply_vsi_submission_metadata.py --apply`.",
            "7. Inspect `main.tex`, `cover_letter.txt`, and `credit_author_statement.txt` before rerunning `make -C manuscript_vsi_biomedical_data release`.",
            "",
            "## Field Ownership",
            "",
            "- Author list, affiliations, corresponding-author details, and CRediT roles: corresponding author and all authors.",
            "- Ethics approval, consent or waiver language, and de-identification statement: PI and institutional compliance office.",
            "- Funding statement and grant numbers: corresponding author, PI, and institutional grants office.",
            "- Final upload consistency: submitting author.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def owner_for(field: str) -> str:
    if field.startswith("ethics."):
        return "PI / institutional compliance office"
    if field.startswith("funding."):
        return "Corresponding author / PI / grants office"
    if field.startswith("author_contributions."):
        return "All authors / corresponding author"
    return "Corresponding author / submitting author"


def existing_approved_values() -> dict[str, str]:
    if not FORM_OUT.exists():
        return {}
    text = FORM_OUT.read_text()
    values: dict[str, str] = {}
    section_pattern = re.compile(r"^### `([^`]+)`\n(.*?)(?=^### `|^## |\Z)", re.M | re.S)
    value_pattern = re.compile(
        r"- Approved final value(?: or confirmed empty)?:\n\n```text\n(.*?)\n```",
        re.S,
    )
    for match in section_pattern.finditer(text):
        value_match = value_pattern.search(match.group(2))
        if value_match:
            values[match.group(1)] = value_match.group(1).strip()
    return values


def write_fill_form(output: list[dict[str, str]], approvals: dict[str, str]) -> None:
    required = [row for row in output if row["required"] == "yes"]
    optional = [row for row in output if row["required"] != "yes"]
    blocker_count = sum(1 for row in required if row["status"] == "BLOCKER")
    lines = [
        "# Submission Metadata Author Fill Form",
        "",
        "This form is for human collection of final author, affiliation, ethics, funding, and CRediT metadata. It does not modify the manuscript. Transfer approved answers into `submission_metadata_template.yaml`, then run the validation commands below.",
        "",
        "## Summary",
        "",
        f"- Required fields listed: {len(required)}",
        f"- Required fields still blocked: {blocker_count}",
        "- Metadata source to update after approval: `submission_metadata_template.yaml`",
        "- Fill-form sync dry-run command: `make -C manuscript_vsi_biomedical_data metadata-fill-sync`",
        "- Author-approved YAML sync command: `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply`",
        "- Dry-run validation command: `make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan`",
        "- Author-approved apply command: `python scripts/apply_vsi_submission_metadata.py --apply`",
        "",
        "## Required Fields To Fill Or Confirm",
        "",
    ]
    for row in required:
        lines.extend(
            [
                f"### `{row['field']}`",
                "",
                f"- Label: {row['label']}",
                f"- Current status: {row['status']}",
                f"- Current value: `{row['current_value']}`",
                f"- Destination: {row['destination']}",
                f"- Owner: {owner_for(row['field'])}",
                f"- Guidance: {row['guidance']}",
                "- Approved final value:",
                "",
                "```text",
                approvals.get(row["field"], ""),
                "```",
                "",
            ]
        )

    lines.extend(["## Optional Fields", ""])
    for row in optional:
        lines.extend(
            [
                f"### `{row['field']}`",
                "",
                f"- Label: {row['label']}",
                f"- Current status: {row['status']}",
                f"- Current value: `{row['current_value']}`",
                f"- Destination: {row['destination']}",
                f"- Owner: {owner_for(row['field'])}",
                f"- Guidance: {row['guidance']}",
                "- Approved final value or confirmed empty:",
                "",
                "```text",
                approvals.get(row["field"], ""),
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## After Filling",
            "",
            "1. Run `make -C manuscript_vsi_biomedical_data metadata-fill-sync` to audit the approved values without changing YAML.",
            "2. Run `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply` after final approval, or copy approved values into `submission_metadata_template.yaml` manually.",
            "3. Run `make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan`.",
            "4. Require zero required metadata blockers before applying metadata to manuscript files.",
            "5. Run `python scripts/apply_vsi_submission_metadata.py --apply` only after final author approval.",
            "6. Rerun `make -C manuscript_vsi_biomedical_data release` and require the verifier to report `Status: **READY**` before upload.",
            "",
        ]
    )
    FORM_OUT.write_text("\n".join(lines))


def main() -> None:
    data = load_metadata()
    output = rows(data)
    approvals = existing_approved_values()
    write_csv(output)
    write_markdown(output)
    write_fill_form(output, approvals)
    required_blockers = sum(1 for row in output if row["required"] == "yes" and row["status"] == "BLOCKER")
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {FORM_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Submission metadata completion packet: required_blockers={required_blockers}")


if __name__ == "__main__":
    main()
