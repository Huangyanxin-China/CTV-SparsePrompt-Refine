#!/usr/bin/env python3
"""Sync approved metadata values from the human fill form into YAML.

Default mode is read-only. Use --apply only after the corresponding author,
PI/compliance office, grants office, and authors have approved the values in
submission_metadata_author_fill_form.md.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
METADATA = PKG / "submission_metadata_template.yaml"
FILL_FORM = PKG / "submission_metadata_author_fill_form.md"
MD_OUT = PKG / "submission_metadata_fill_form_sync.md"
CSV_OUT = ROOT / "reports" / "vsi_submission_metadata_fill_form_sync_20260531.csv"

PLACEHOLDER_MARKERS = [
    "TODO_REPLACE",
    "TODO_REPLACE_OR_LEAVE_EMPTY",
    "to be finalized",
    "Institution to be finalized",
    "corresponding.email",
]


@dataclass(frozen=True)
class FieldDef:
    path: str
    label: str
    required: bool
    kind: str = "text"


@dataclass(frozen=True)
class SyncRow:
    field: str
    label: str
    required: str
    status: str
    source: str
    action: str


FIELDS = [
    FieldDef("authors.0.name", "First author name", True),
    FieldDef("authors.0.email", "First author email", True, "email"),
    FieldDef("authors.0.orcid", "First author ORCID", False, "orcid"),
    FieldDef("affiliations.0.organization", "Affiliation organization", True),
    FieldDef("affiliations.0.city", "Affiliation city", True),
    FieldDef("affiliations.0.country", "Affiliation country", True),
    FieldDef("corresponding_author.name", "Corresponding author name", True),
    FieldDef("corresponding_author.email", "Corresponding author email", True, "email"),
    FieldDef("corresponding_author.address", "Corresponding author address", True),
    FieldDef("ethics.approval_body", "Ethics approval body", True),
    FieldDef("ethics.approval_number", "Ethics approval number or exemption", True),
    FieldDef("ethics.consent_or_waiver", "Consent or waiver language", True),
    FieldDef("ethics.deidentification_statement", "De-identification statement", True),
    FieldDef("funding.statement", "Funding statement", True),
    FieldDef("funding.grant_numbers", "Grant numbers", False, "list"),
    FieldDef("author_contributions.conceptualization", "CRediT: Conceptualization", True),
    FieldDef("author_contributions.methodology", "CRediT: Methodology", True),
    FieldDef("author_contributions.software", "CRediT: Software", True),
    FieldDef("author_contributions.validation", "CRediT: Validation", True),
    FieldDef("author_contributions.investigation", "CRediT: Investigation", True),
    FieldDef("author_contributions.writing_original_draft", "CRediT: Writing - original draft", True),
    FieldDef("author_contributions.writing_review_editing", "CRediT: Writing - review and editing", True),
    FieldDef("author_contributions.supervision", "CRediT: Supervision", True),
]


def load_yaml() -> tuple[dict[str, Any], str]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}, "PyYAML is not available"
    try:
        data = yaml.safe_load(METADATA.read_text())
    except Exception as exc:
        return {}, f"YAML parse error: {exc}"
    if not isinstance(data, dict):
        return {}, "YAML top level is not a mapping"
    return data, ""


def dump_yaml(data: dict[str, Any]) -> str:
    import yaml  # type: ignore

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False, width=1000)


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


def set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    cur: Any = data
    parts = dotted.split(".")
    for part, nxt in zip(parts[:-1], parts[1:]):
        if isinstance(cur, dict):
            if part not in cur or cur[part] is None:
                cur[part] = [] if nxt.isdigit() else {}
            cur = cur[part]
        elif isinstance(cur, list):
            index = int(part)
            while len(cur) <= index:
                cur.append({} if not nxt.isdigit() else [])
            cur = cur[index]
        else:
            raise ValueError(f"Cannot descend into {dotted}")
    last = parts[-1]
    if isinstance(cur, dict):
        cur[last] = value
    elif isinstance(cur, list):
        index = int(last)
        while len(cur) <= index:
            cur.append(None)
        cur[index] = value
    else:
        raise ValueError(f"Cannot set {dotted}")


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value).strip()


def has_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or any(marker in stripped for marker in PLACEHOLDER_MARKERS)
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    return False


def approved_values() -> dict[str, str]:
    if not FILL_FORM.exists():
        return {}
    text = FILL_FORM.read_text()
    values: dict[str, str] = {}
    section_pattern = re.compile(r"^### `([^`]+)`\n(.*?)(?=^### `|^## |\Z)", re.M | re.S)
    value_pattern = re.compile(
        r"- Approved final value(?: or confirmed empty)?:\n\n```text\n(.*?)\n```",
        re.S,
    )
    for match in section_pattern.finditer(text):
        field = match.group(1)
        body = match.group(2)
        value_match = value_pattern.search(body)
        if value_match:
            values[field] = value_match.group(1).strip()
    return values


def email_ok(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()))


def orcid_ok(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    return bool(re.fullmatch(r"\d{4}-\d{4}-\d{4}-[\dX]{4}", stripped))


def normalize(field: FieldDef, value: str) -> Any:
    stripped = value.strip()
    if field.kind == "list":
        if not stripped:
            return []
        return [
            item.strip().lstrip("-").strip()
            for item in re.split(r"[\n,]", stripped)
            if item.strip().lstrip("-").strip()
        ]
    if field.kind == "orcid" and not stripped:
        return ""
    return stripped


def validate_value(field: FieldDef, value: str) -> tuple[bool, str]:
    if any(marker in value for marker in PLACEHOLDER_MARKERS):
        return False, "Approved value still contains a placeholder marker."
    if field.kind == "email" and not email_ok(value):
        return False, "Approved value is not a valid email-like string."
    if field.kind == "orcid" and not orcid_ok(value):
        return False, "Approved ORCID must be blank or match 0000-0000-0000-0000."
    if field.required and not value.strip():
        return False, "Required approved value is empty."
    return True, "Ready."


def build_sync(data: dict[str, Any], approvals: dict[str, str]) -> tuple[list[SyncRow], dict[str, Any], int]:
    rows: list[SyncRow] = []
    updates: dict[str, Any] = {}
    blockers = 0

    for field in FIELDS:
        approved = approvals.get(field.path, "").strip()
        current = get_path(data, field.path)
        current_ready = not has_placeholder(current)

        if approved:
            valid, detail = validate_value(field, approved)
            if valid:
                rows.append(
                    SyncRow(field.path, field.label, "yes" if field.required else "no", "READY_FROM_FORM", "approved fill-form value", "Will update YAML on --apply.")
                )
                updates[field.path] = normalize(field, approved)
            else:
                blockers += 1
                rows.append(
                    SyncRow(field.path, field.label, "yes" if field.required else "no", "BLOCKER_INVALID_APPROVED_VALUE", "approved fill-form value", detail)
                )
            continue

        if field.required and current_ready:
            rows.append(
                SyncRow(field.path, field.label, "yes", "READY_FROM_TEMPLATE", "existing YAML value", "No form value supplied; existing non-placeholder YAML value will be preserved.")
            )
            continue

        if not field.required:
            if field.kind in {"orcid", "list"} and has_placeholder(current):
                rows.append(
                    SyncRow(field.path, field.label, "no", "OPTIONAL_EMPTY_WILL_CLEAR_PLACEHOLDER", "blank optional fill-form value", "Will clear optional placeholder on --apply after required blockers are resolved.")
                )
                updates[field.path] = normalize(field, "")
            else:
                rows.append(
                    SyncRow(field.path, field.label, "no", "OPTIONAL_EMPTY_OR_PRESERVED", "blank optional fill-form value", "No required action.")
                )
            continue

        blockers += 1
        rows.append(
            SyncRow(field.path, field.label, "yes", "BLOCKER_EMPTY_APPROVED_VALUE", "missing approved fill-form value", "Fill this value in submission_metadata_author_fill_form.md or in submission_metadata_template.yaml.")
        )

    return rows, updates, blockers


def write_outputs(rows: list[SyncRow], blockers: int, apply_requested: bool, applied: bool) -> None:
    status = "APPLIED" if applied else "READY_TO_APPLY" if blockers == 0 else "BLOCKED_BY_EMPTY_APPROVED_VALUES"
    ready_count = sum(1 for row in rows if row.status.startswith("READY"))
    optional_count = sum(1 for row in rows if row.required == "no")
    lines = [
        "# Submission Metadata Fill-Form Sync",
        "",
        "This report validates whether approved values in `submission_metadata_author_fill_form.md` can be synchronized into `submission_metadata_template.yaml`. It does not print approved values, so author emails, addresses, ethics identifiers, and grant details are not duplicated in this audit file.",
        "",
        "## Summary",
        "",
        f"- Sync status: {status}",
        f"- Apply requested: {'YES' if apply_requested else 'NO'}",
        f"- YAML modified: {'YES' if applied else 'NO'}",
        f"- Required/ready rows: {ready_count}",
        f"- Optional rows: {optional_count}",
        f"- Blocking rows: {blockers}",
        "- Dry-run command: `make -C manuscript_vsi_biomedical_data metadata-fill-sync`",
        "- Author-approved YAML sync command: `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply`",
        "- Post-sync validation command: `make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan`",
        "- Manuscript propagation command after final author approval: `python scripts/apply_vsi_submission_metadata.py --apply`",
        "",
        "## Field Sync Rows",
        "",
        "| Field | Label | Required | Status | Source | Action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = [row.field, row.label, row.required, row.status, row.source, row.action]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## Completion Rule",
            "",
            "- Run the `--apply` command only after all approved values in the fill form have human approval.",
            "- The script refuses to write YAML while any required row remains blocked.",
            "- After YAML sync, rerun metadata preflight, lock audit, metadata application dry-run, and the full release target.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))

    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["field", "label", "required", "status", "source", "action"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync approved fill-form metadata into submission_metadata_template.yaml.")
    parser.add_argument("--apply", action="store_true", help="Write approved fill-form values into submission_metadata_template.yaml.")
    args = parser.parse_args()

    data, error = load_yaml()
    if error:
        row = SyncRow("submission_metadata_template.yaml", "Metadata YAML", "yes", "BLOCKER_YAML", "metadata file", error)
        write_outputs([row], blockers=1, apply_requested=args.apply, applied=False)
        raise SystemExit(error)

    approvals = approved_values()
    rows, updates, blockers = build_sync(data, approvals)
    applied = False
    if args.apply:
        if blockers:
            write_outputs(rows, blockers=blockers, apply_requested=True, applied=False)
            raise SystemExit("Refusing to sync metadata while required fill-form blockers remain.")
        for dotted, value in updates.items():
            set_path(data, dotted, value)
        METADATA.write_text(dump_yaml(data))
        applied = True

    write_outputs(rows, blockers=blockers, apply_requested=args.apply, applied=applied)
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Fill-form sync status: {'APPLIED' if applied else 'DRY_RUN'}; blockers={blockers}")


if __name__ == "__main__":
    main()
