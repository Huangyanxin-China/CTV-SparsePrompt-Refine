#!/usr/bin/env python3
"""Create a metadata-lock audit for final Editorial Manager submission fields."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
METADATA = PKG / "submission_metadata_template.yaml"
PREFLIGHT = PKG / "submission_metadata_preflight.md"
MAIN_TEX = PKG / "main.tex"
COVER_LETTER = PKG / "cover_letter.txt"
OUT_MD = PKG / "submission_metadata_lock_audit.md"
OUT_CSV = ROOT / "reports" / "vsi_submission_metadata_lock_audit_20260531.csv"

PLACEHOLDER_MARKERS = [
    "TODO_REPLACE",
    "TODO_REPLACE_OR_LEAVE_EMPTY",
    "to be finalized",
    "Institution to be finalized",
    "corresponding.email",
    "city={City}",
    "country={Country}",
    "must be inserted",
    "should be finalized",
]


@dataclass(frozen=True)
class FieldMap:
    dotted: str
    label: str
    targets: str
    required: bool
    action: str


FIELD_MAPS = [
    FieldMap("target_journal", "Journal", "Editorial Manager journal field", True, "Keep as Pattern Recognition."),
    FieldMap("special_issue", "Special issue", "Editorial Manager special-issue context", True, "Keep official special issue name."),
    FieldMap("article_type", "Article type", "Editorial Manager article-type selector", True, "Select VSI: PR_Biomedical Data."),
    FieldMap("manuscript.title", "Title", "main.tex title and metadata form", True, "Keep title synchronized."),
    FieldMap("authors.0.name", "First author name", "main.tex author block and metadata form", True, "Confirm final spelling and order."),
    FieldMap("authors.0.email", "First author email", "metadata form", True, "Replace placeholder with final email."),
    FieldMap("authors.0.orcid", "First author ORCID", "metadata form", False, "Use valid ORCID or leave blank."),
    FieldMap("affiliations.0.organization", "Affiliation organization", "main.tex affiliation and metadata form", True, "Insert institution name."),
    FieldMap("affiliations.0.city", "Affiliation city", "main.tex affiliation and metadata form", True, "Insert institution city."),
    FieldMap("affiliations.0.country", "Affiliation country", "main.tex affiliation and metadata form", True, "Insert institution country."),
    FieldMap("corresponding_author.name", "Corresponding author name", "main.tex cormark and cover letter", True, "Confirm final corresponding author."),
    FieldMap("corresponding_author.email", "Corresponding author email", "main.tex ead, cover letter, metadata form", True, "Replace placeholder with final email."),
    FieldMap("corresponding_author.address", "Corresponding author address", "cover letter and metadata form", True, "Insert postal address."),
    FieldMap("ethics.approval_body", "Ethics approval body", "main.tex Ethics Statement and metadata form", True, "Insert IRB or ethics committee name."),
    FieldMap("ethics.approval_number", "Ethics approval number", "main.tex Ethics Statement and metadata form", True, "Insert approval number or exemption."),
    FieldMap("ethics.consent_or_waiver", "Consent or waiver", "main.tex Ethics Statement and metadata form", True, "Insert consent, waiver, or retrospective data language."),
    FieldMap("funding.statement", "Funding statement", "main.tex Acknowledgements and metadata form", True, "Insert funding or no-specific-funding statement."),
    FieldMap("author_contributions.conceptualization", "CRediT conceptualization", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role."),
    FieldMap("author_contributions.methodology", "CRediT methodology", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role."),
    FieldMap("author_contributions.software", "CRediT software", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role."),
    FieldMap("author_contributions.validation", "CRediT validation", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role."),
    FieldMap("author_contributions.investigation", "CRediT investigation", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role."),
    FieldMap("author_contributions.writing_original_draft", "CRediT writing original draft", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role."),
    FieldMap("author_contributions.writing_review_editing", "CRediT writing review editing", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role."),
    FieldMap("author_contributions.supervision", "CRediT supervision", "credit_author_statement.txt and main.tex", True, "Insert final author-specific role or not applicable."),
]


def sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def load_yaml(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text()
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}, text
    try:
        data = yaml.safe_load(text)
    except Exception:
        return {}, text
    return (data if isinstance(data, dict) else {}), text


def get_path(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return cur


def has_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        return any(marker in stripped for marker in PLACEHOLDER_MARKERS)
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    return False


def scalar(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, list):
        return f"list with {len(value)} item(s)"
    if isinstance(value, dict):
        return f"dict with {len(value)} item(s)"
    return str(value)


def email_like(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()))


def orcid_ok(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return True
    return bool(re.fullmatch(r"\d{4}-\d{4}-\d{4}-[\dX]{4}", stripped))


def file_placeholder_hits(path: Path) -> list[str]:
    hits = []
    text = path.read_text() if path.exists() else ""
    for idx, line in enumerate(text.splitlines(), 1):
        if any(marker in line for marker in PLACEHOLDER_MARKERS):
            hits.append(f"{path.name}:{idx}")
    return hits


def preflight_blocker_count() -> int | None:
    if not PREFLIGHT.exists():
        return None
    match = re.search(r"Blocking metadata checks:\s*(\d+)", PREFLIGHT.read_text())
    if not match:
        return None
    return int(match.group(1))


def field_status(field: FieldMap, data: dict[str, Any]) -> tuple[str, str]:
    value = get_path(data, field.dotted)
    if field.dotted.endswith("email") and not email_like(value):
        return "BLOCKER", scalar(value)
    if field.dotted.endswith("orcid") and not orcid_ok(value):
        return "BLOCKER", scalar(value)
    if field.required and has_placeholder(value):
        return "BLOCKER", scalar(value)
    if not field.required and has_placeholder(value):
        return "WARNING", scalar(value)
    return "PASS", scalar(value)


def build_rows(data: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for field in FIELD_MAPS:
        status, value = field_status(field, data)
        rows.append(
            {
                "metadata_path": field.dotted,
                "label": field.label,
                "status": status,
                "current_value": value,
                "targets": field.targets,
                "required_action": field.action,
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["metadata_path", "label", "status", "current_value", "targets", "required_action"],
        )
        writer.writeheader()
        writer.writerows(rows)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def write_markdown(rows: list[dict[str, str]], raw_metadata: str) -> None:
    blocker_count = sum(1 for row in rows if row["status"] == "BLOCKER")
    warning_count = sum(1 for row in rows if row["status"] == "WARNING")
    preflight_blockers = preflight_blocker_count()
    main_hits = file_placeholder_hits(MAIN_TEX)
    cover_hits = file_placeholder_hits(COVER_LETTER)
    metadata_placeholder_count = sum(1 for marker in PLACEHOLDER_MARKERS if marker in raw_metadata)
    ready = blocker_count == 0 and not main_hits and not cover_hits and preflight_blockers == 0
    status = "READY_FOR_METADATA_LOCK" if ready else "NOT_READY_FOR_METADATA_LOCK"
    lines = [
        "# Submission Metadata Lock Audit",
        "",
        "This audit maps final Editorial Manager metadata fields to local manuscript files. It is intentionally read-only: it does not replace author, ethics, funding, or CRediT placeholders automatically.",
        "",
        "## Summary",
        "",
        f"- Status: {status}",
        f"- Metadata field blockers: {blocker_count}",
        f"- Metadata field warnings: {warning_count}",
        f"- Preflight blocker count: {preflight_blockers if preflight_blockers is not None else 'not available'}",
        f"- main.tex placeholder hit count: {len(main_hits)}",
        f"- cover_letter.txt placeholder hit count: {len(cover_hits)}",
        f"- Metadata placeholder marker types present: {metadata_placeholder_count}",
        f"- Metadata template SHA256 prefix: `{sha256_prefix(METADATA)}`",
        "- Final verification command: `make -C manuscript_vsi_biomedical_data release`",
        "",
        "## Lock Gate",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
        f"| Metadata fields contain no blockers | {'PASS' if blocker_count == 0 else 'BLOCKER'} | {blocker_count} blocker(s) |",
        f"| Submission preflight reports zero blockers | {'PASS' if preflight_blockers == 0 else 'BLOCKER'} | {preflight_blockers if preflight_blockers is not None else 'not available'} blocker(s) |",
        f"| main.tex contains no metadata placeholders | {'PASS' if not main_hits else 'BLOCKER'} | {', '.join(main_hits[:8]) if main_hits else 'none'} |",
        f"| cover_letter.txt contains no signature placeholders | {'PASS' if not cover_hits else 'BLOCKER'} | {', '.join(cover_hits[:8]) if cover_hits else 'none'} |",
        "",
        "## Field Mapping",
        "",
        "| Metadata path | Field | Status | Current value | Targets | Required action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['metadata_path']}`",
                    escape_md(row["label"]),
                    row["status"],
                    escape_md(row["current_value"]),
                    escape_md(row["targets"]),
                    escape_md(row["required_action"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Finalization Workflow",
            "",
            "1. Fill `submission_metadata_template.yaml` with final author, affiliation, corresponding-author, ethics, funding, and CRediT information.",
            "2. Propagate the same confirmed information into `main.tex`, `cover_letter.txt`, and `credit_author_statement.txt`.",
            "3. Run `make -C manuscript_vsi_biomedical_data metadata metadata-lock blockers release`.",
            "4. Proceed to TeX/PDF compilation only after this audit and `submission_metadata_preflight.md` both report ready status.",
            "",
            "## Interpretation",
            "",
            "- `READY_FOR_METADATA_LOCK` means the submission metadata can be copied into Editorial Manager after final PDF inspection.",
            "- `NOT_READY_FOR_METADATA_LOCK` means the remaining human-supplied metadata still prevents a real submission.",
            "- This audit deliberately refuses to infer missing institutional information from context.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    data, raw_metadata = load_yaml(METADATA)
    rows = build_rows(data)
    write_csv(rows)
    write_markdown(rows, raw_metadata)
    blocker_count = sum(1 for row in rows if row["status"] == "BLOCKER")
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(f"Metadata lock blockers: {blocker_count}")


if __name__ == "__main__":
    main()
