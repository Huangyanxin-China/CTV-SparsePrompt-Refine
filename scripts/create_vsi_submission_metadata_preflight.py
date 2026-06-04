#!/usr/bin/env python3
"""Create a metadata preflight report for the VSI submission package."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
METADATA = PKG / "submission_metadata_template.yaml"
OUT = PKG / "submission_metadata_preflight.md"

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
class Check:
    name: str
    status: str
    evidence: str
    resolution: str


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
            except (ValueError, IndexError):
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


def scalar_text(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, (list, dict)):
        return f"{type(value).__name__} with {len(value)} item(s)"
    return str(value)


def ok_or_blocker(ok: bool) -> str:
    return "PASS" if ok else "BLOCKER"


def line_hits(path: Path, markers: list[str]) -> list[str]:
    if not path.exists():
        return [f"{path.name}: missing"]
    hits = []
    for idx, line in enumerate(path.read_text().splitlines(), 1):
        if any(marker in line for marker in markers):
            snippet = " ".join(line.strip().split())
            hits.append(f"{path.name}:{idx} {snippet}")
    return hits


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


def final_orcid_ok(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    if any(marker in value for marker in PLACEHOLDER_MARKERS):
        return False
    return orcid_ok(value)


def field_check(data: dict[str, Any], dotted: str, label: str, resolution: str) -> Check:
    value = get_path(data, dotted)
    ok = not has_placeholder(value)
    return Check(label, ok_or_blocker(ok), scalar_text(value), resolution)


def file_check(rel: str) -> Check:
    path = PKG / rel
    return Check(
        f"File present: {rel}",
        ok_or_blocker(path.exists()),
        rel if path.exists() else "missing",
        "Create or restore the required file.",
    )


def build_checks(data: dict[str, Any], raw_metadata: str) -> list[Check]:
    checks: list[Check] = []
    checks.extend(
        [
            Check(
                "Target journal is Pattern Recognition",
                ok_or_blocker(get_path(data, "target_journal") == "Pattern Recognition"),
                scalar_text(get_path(data, "target_journal")),
                "Set target_journal to Pattern Recognition.",
            ),
            Check(
                "Article type is VSI: PR_Biomedical Data",
                ok_or_blocker(get_path(data, "article_type") == "VSI: PR_Biomedical Data"),
                scalar_text(get_path(data, "article_type")),
                "Select and record VSI: PR_Biomedical Data.",
            ),
            Check(
                "Special issue name is present",
                ok_or_blocker("Multimodal Pattern Recognition for Biomedical Data" in scalar_text(get_path(data, "special_issue"))),
                scalar_text(get_path(data, "special_issue")),
                "Record the official special issue name.",
            ),
        ]
    )

    for rel in [
        "main.tex",
        "references.bib",
        "highlights.tex",
        "cover_letter.txt",
        "data_availability_statement.txt",
        "declaration_of_interest.txt",
        "generative_ai_statement.txt",
        "credit_author_statement.txt",
    ]:
        checks.append(file_check(rel))

    checks.extend(
        [
            field_check(data, "authors.0.name", "First author name present", "Enter final first author name."),
            field_check(data, "authors.0.email", "First author email finalized", "Replace author email placeholder."),
            Check(
                "First author email has email form",
                ok_or_blocker(email_like(get_path(data, "authors.0.email"))),
                scalar_text(get_path(data, "authors.0.email")),
                "Use a valid author email address.",
            ),
            Check(
                "First author ORCID blank or valid",
                ok_or_blocker(final_orcid_ok(get_path(data, "authors.0.orcid"))),
                scalar_text(get_path(data, "authors.0.orcid")),
                "Replace the ORCID placeholder with a valid ORCID or leave the field empty.",
            ),
            field_check(data, "affiliations.0.organization", "Affiliation organization finalized", "Insert institution name."),
            field_check(data, "affiliations.0.city", "Affiliation city finalized", "Insert institution city."),
            field_check(data, "affiliations.0.country", "Affiliation country finalized", "Insert institution country."),
            field_check(data, "corresponding_author.name", "Corresponding author name finalized", "Insert corresponding author name."),
            field_check(data, "corresponding_author.email", "Corresponding author email finalized", "Insert corresponding author email."),
            Check(
                "Corresponding author email has email form",
                ok_or_blocker(email_like(get_path(data, "corresponding_author.email"))),
                scalar_text(get_path(data, "corresponding_author.email")),
                "Use a valid corresponding author email address.",
            ),
            field_check(data, "corresponding_author.address", "Corresponding author address finalized", "Insert postal address."),
            field_check(data, "ethics.approval_body", "Ethics approval body finalized", "Insert IRB or ethics committee name."),
            field_check(data, "ethics.approval_number", "Ethics approval number or exemption finalized", "Insert approval number or exemption statement."),
            field_check(data, "ethics.consent_or_waiver", "Consent or waiver language finalized", "Insert consent, waiver, or retrospective de-identified-data language."),
            field_check(data, "funding.statement", "Funding statement finalized", "Insert grant statement or no-specific-funding statement."),
        ]
    )

    for role in [
        "conceptualization",
        "methodology",
        "software",
        "validation",
        "investigation",
        "writing_original_draft",
        "writing_review_editing",
        "supervision",
    ]:
        checks.append(field_check(data, f"author_contributions.{role}", f"CRediT role finalized: {role}", "Insert final author-specific CRediT roles."))

    metadata_placeholders = [marker for marker in PLACEHOLDER_MARKERS if marker in raw_metadata]
    checks.append(
        Check(
            "Metadata YAML has no placeholder markers",
            ok_or_blocker(not metadata_placeholders),
            ", ".join(metadata_placeholders) if metadata_placeholders else "none",
            "Replace all TODO and placeholder metadata values.",
        )
    )

    tex_hits = line_hits(PKG / "main.tex", PLACEHOLDER_MARKERS)
    checks.append(
        Check(
            "main.tex has no submission placeholders",
            ok_or_blocker(not tex_hits),
            "<br>".join(tex_hits[:8]) if tex_hits else "none",
            "Propagate final metadata into main.tex.",
        )
    )
    cover_hits = line_hits(PKG / "cover_letter.txt", ["to be finalized"])
    checks.append(
        Check(
            "cover letter has finalized corresponding author details",
            ok_or_blocker(not cover_hits),
            "<br>".join(cover_hits) if cover_hits else "none",
            "Update the cover-letter signature block.",
        )
    )
    return checks


def render(checks: list[Check]) -> str:
    blockers = [item for item in checks if item.status == "BLOCKER"]
    status = "READY_FOR_METADATA_LOCK" if not blockers else "NOT_READY_FOR_METADATA_LOCK"
    lines = [
        "# Submission Metadata Preflight",
        "",
        "This report validates whether `submission_metadata_template.yaml` and the manuscript-facing metadata fields are ready to be locked for final Editorial Manager entry.",
        "",
        f"- Status: {status}",
        f"- Blocking metadata checks: {len(blockers)}",
        "- Final verification command after metadata resolution: `make -C manuscript_vsi_biomedical_data release`",
        "",
        "## Required Metadata Checks",
        "",
        "| Check | Status | Evidence | Required resolution |",
        "| --- | --- | --- | --- |",
    ]
    for check in checks:
        evidence = check.evidence.replace("|", "\\|")
        resolution = check.resolution.replace("|", "\\|")
        lines.append(f"| {check.name} | {check.status} | {evidence} | {resolution} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `READY_FOR_METADATA_LOCK` means metadata placeholders are resolved and the package can move to final author/PDF checks.",
            "- `NOT_READY_FOR_METADATA_LOCK` means missing metadata still prevents a real journal submission.",
            "- This preflight does not replace institutional review, author approval, publisher-record citation verification, or compiled-PDF inspection.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    data, raw_metadata = load_yaml(METADATA)
    checks = build_checks(data, raw_metadata)
    report = render(checks)
    OUT.write_text(report)
    blockers = sum(1 for item in checks if item.status == "BLOCKER")
    print(f"Wrote {OUT}")
    print(f"Blocking metadata checks: {blockers}")


if __name__ == "__main__":
    main()
