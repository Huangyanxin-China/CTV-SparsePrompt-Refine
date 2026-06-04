#!/usr/bin/env python3
"""Prepare or apply finalized submission metadata across the VSI package.

Default mode is read-only and writes an application plan. Use --apply only after
submission_metadata_template.yaml has been completed and institutionally
approved.
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
PLAN_OUT = PKG / "metadata_application_plan.md"
CSV_OUT = ROOT / "reports" / "vsi_metadata_application_plan_20260531.csv"

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
class PlanRow:
    target: str
    status: str
    detail: str
    action: str


def load_yaml() -> tuple[dict[str, Any], str, str]:
    raw = METADATA.read_text()
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}, raw, "PyYAML is not available"
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:  # pragma: no cover - depends on local YAML parser
        return {}, raw, f"YAML parse error: {exc}"
    if not isinstance(data, dict):
        return {}, raw, "YAML top level is not a mapping"
    return data, raw, ""


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


def as_text(value: Any) -> str:
    if value is None:
        return ""
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


def email_like(value: Any) -> bool:
    text = as_text(value)
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def author_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    authors = get_path(data, "authors")
    return authors if isinstance(authors, list) else []


def affiliation_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    affiliations = get_path(data, "affiliations")
    return affiliations if isinstance(affiliations, list) else []


def contributions(data: dict[str, Any]) -> dict[str, str]:
    raw = get_path(data, "author_contributions")
    if not isinstance(raw, dict):
        return {}
    return {str(key): as_text(value) for key, value in raw.items()}


def validate_metadata(data: dict[str, Any], raw: str, parse_error: str) -> list[PlanRow]:
    rows: list[PlanRow] = []
    if parse_error:
        rows.append(PlanRow("submission_metadata_template.yaml", "BLOCKER", parse_error, "Install PyYAML or fix YAML syntax."))
        return rows

    required_paths = [
        ("target_journal", "Pattern Recognition"),
        ("article_type", "VSI: PR_Biomedical Data"),
        ("manuscript.title", "final title"),
        ("authors.0.name", "first author name"),
        ("authors.0.email", "first author email"),
        ("affiliations.0.organization", "affiliation organization"),
        ("affiliations.0.city", "affiliation city"),
        ("affiliations.0.country", "affiliation country"),
        ("corresponding_author.name", "corresponding author name"),
        ("corresponding_author.email", "corresponding author email"),
        ("corresponding_author.address", "corresponding author address"),
        ("ethics.approval_body", "ethics approval body"),
        ("ethics.approval_number", "ethics approval number or exemption"),
        ("ethics.consent_or_waiver", "consent or waiver language"),
        ("funding.statement", "funding statement"),
        ("author_contributions.conceptualization", "CRediT conceptualization"),
        ("author_contributions.methodology", "CRediT methodology"),
        ("author_contributions.software", "CRediT software"),
        ("author_contributions.validation", "CRediT validation"),
        ("author_contributions.investigation", "CRediT investigation"),
        ("author_contributions.writing_original_draft", "CRediT writing original draft"),
        ("author_contributions.writing_review_editing", "CRediT writing review editing"),
        ("author_contributions.supervision", "CRediT supervision"),
    ]
    for dotted, label in required_paths:
        value = get_path(data, dotted)
        if has_placeholder(value):
            rows.append(PlanRow(dotted, "BLOCKER", f"Missing or placeholder value for {label}", "Fill this field in submission_metadata_template.yaml."))
        else:
            rows.append(PlanRow(dotted, "PASS", f"{label} present", "No action."))

    for dotted in ["authors.0.email", "corresponding_author.email"]:
        value = get_path(data, dotted)
        rows.append(
            PlanRow(
                dotted,
                "PASS" if email_like(value) else "BLOCKER",
                as_text(value) or "missing",
                "Use a valid email address.",
            )
        )

    placeholder_markers = [marker for marker in PLACEHOLDER_MARKERS if marker in raw]
    rows.append(
        PlanRow(
            "submission_metadata_template.yaml",
            "PASS" if not placeholder_markers else "BLOCKER",
            ", ".join(placeholder_markers) if placeholder_markers else "no placeholder markers",
            "Remove placeholders before applying metadata.",
        )
    )
    return rows


def build_author_front_matter(data: dict[str, Any]) -> str:
    corr_name = as_text(get_path(data, "corresponding_author.name"))
    corr_email = as_text(get_path(data, "corresponding_author.email"))
    blocks: list[str] = []
    for author in author_list(data):
        name = tex_escape(as_text(author.get("name")))
        affiliation_id = tex_escape(as_text(author.get("affiliation_id") or "1"))
        blocks.append(f"\\author[{affiliation_id}]{{{name}}}")
        if as_text(author.get("name")) == corr_name:
            blocks.append(r"\cormark[1]")
            blocks.append(f"\\ead{{{corr_email}}}")
        blocks.append("")

    for aff in affiliation_list(data):
        aff_id = tex_escape(as_text(aff.get("id") or "1"))
        organization = tex_escape(as_text(aff.get("organization")))
        city = tex_escape(as_text(aff.get("city")))
        country = tex_escape(as_text(aff.get("country")))
        blocks.extend(
            [
                f"\\affiliation[{aff_id}]{{",
                f"  organization={{{organization}}},",
                f"  city={{{city}}},",
                f"  country={{{country}}}",
                "}",
                "",
            ]
        )
    blocks.append(r"\cortext[cor1]{Corresponding author.}")
    return "\n".join(blocks).strip()


def build_ethics_text(data: dict[str, Any]) -> str:
    body = as_text(get_path(data, "ethics.approval_body"))
    number = as_text(get_path(data, "ethics.approval_number"))
    consent = as_text(get_path(data, "ethics.consent_or_waiver"))
    deid = as_text(get_path(data, "ethics.deidentification_statement"))
    sentence = f"This retrospective study was reviewed by {body} ({number}). {consent}"
    if deid:
        sentence += f" {deid}"
    return sentence.strip()


def build_credit_text(data: dict[str, Any]) -> str:
    contrib = contributions(data)
    role_names = {
        "conceptualization": "Conceptualization",
        "methodology": "Methodology",
        "software": "Software",
        "validation": "Validation",
        "investigation": "Investigation",
        "writing_original_draft": "Writing - original draft",
        "writing_review_editing": "Writing - review and editing",
        "supervision": "Supervision",
    }
    parts = []
    for key, label in role_names.items():
        value = contrib.get(key, "")
        if value:
            parts.append(f"{label}: {value}")
    return "; ".join(parts) + "."


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Could not locate block between {start!r} and {end!r}")
    return text[: match.start()] + start + "\n\n" + replacement.strip() + "\n\n" + end + text[match.end() :]


def planned_updates(data: dict[str, Any]) -> dict[str, str]:
    main_path = PKG / "main.tex"
    main = main_path.read_text()
    title = tex_escape(as_text(get_path(data, "manuscript.title")))
    main = re.sub(
        r"\\title\[mode=title\]\{.*?\}",
        lambda _match: f"\\title[mode=title]{{{title}}}",
        main,
        count=1,
        flags=re.S,
    )
    front_matter = build_author_front_matter(data)
    main = re.sub(
        r"\\author\[1\]\{Yanxin Huang\}.*?\\cortext\[cor1\]\{Corresponding author\.\}",
        lambda _match: front_matter,
        main,
        count=1,
        flags=re.S,
    )
    main = replace_between(main, r"\section*{Ethics Statement}", r"\section*{Data Availability}", build_ethics_text(data))
    main = replace_between(main, r"\section*{CRediT Author Statement}", r"\section*{Declaration of Generative AI and AI-Assisted Technologies in the Manuscript Preparation Process}", build_credit_text(data))
    funding_statement = as_text(get_path(data, "funding.statement"))
    main = replace_between(main, r"\section*{Acknowledgements}", r"\bibliographystyle{cas-model2-names}", funding_statement)

    cover = (PKG / "cover_letter.txt").read_text()
    corr_name = as_text(get_path(data, "corresponding_author.name"))
    corr_email = as_text(get_path(data, "corresponding_author.email"))
    corr_address = as_text(get_path(data, "corresponding_author.address"))
    signoff = f"Sincerely,\n\n{corr_name}\nCorresponding author\n{corr_email}\n{corr_address}"
    cover = re.sub(r"Sincerely,\n\n.*", signoff, cover, count=1, flags=re.S)

    credit = "CRediT author statement\n\n" + build_credit_text(data) + "\n"

    return {
        "main.tex": main,
        "cover_letter.txt": cover,
        "credit_author_statement.txt": credit,
    }


def write_plan(rows: list[PlanRow], updates: dict[str, str], apply_requested: bool, applied: bool) -> None:
    blocker_count = sum(1 for row in rows if row.status == "BLOCKER")
    if blocker_count:
        status = "BLOCKED_BY_PLACEHOLDERS"
    elif applied:
        status = "APPLIED"
    elif apply_requested:
        status = "READY_BUT_NOT_APPLIED"
    else:
        status = "READY_TO_APPLY"

    lines = [
        "# Metadata Application Plan",
        "",
        "This plan validates whether finalized `submission_metadata_template.yaml` fields can be propagated into manuscript-facing submission files. Default mode is read-only.",
        "",
        "## Summary",
        "",
        f"- Status: {status}",
        f"- Apply requested: {'YES' if apply_requested else 'NO'}",
        f"- Files modified: {'YES' if applied else 'NO'}",
        f"- Blocking metadata fields: {blocker_count}",
        "- Apply command after final author approval: `python scripts/apply_vsi_submission_metadata.py --apply`",
        "- Targets: `main.tex`, `cover_letter.txt`, `credit_author_statement.txt`",
        "",
        "## Validation Rows",
        "",
        "| Target | Status | Detail | Action |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(f"| `{row.target}` | {row.status} | {md_escape(row.detail)} | {md_escape(row.action)} |")

    lines.extend(
        [
            "",
            "## Planned File Updates",
            "",
        ]
    )
    for rel, content in updates.items():
        lines.append(f"- `{rel}`: {len(content.splitlines())} lines would be written.")
    if blocker_count:
        lines.extend(
            [
                "",
                "## Interpretation",
                "",
                "- Metadata application is blocked because the YAML still contains placeholders or invalid final fields.",
                "- No manuscript file is modified unless `--apply` is used and all validation rows pass.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Interpretation",
                "",
                "- Metadata can be propagated after final author approval.",
                "- After applying, rerun `make -C manuscript_vsi_biomedical_data release` and inspect the changed manuscript fields.",
                "",
            ]
        )
    PLAN_OUT.write_text("\n".join(lines))

    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target", "status", "detail", "action"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or apply finalized VSI submission metadata.")
    parser.add_argument("--apply", action="store_true", help="Write finalized metadata into manuscript files after validation passes.")
    args = parser.parse_args()

    data, raw, parse_error = load_yaml()
    rows = validate_metadata(data, raw, parse_error)
    blocker_count = sum(1 for row in rows if row.status == "BLOCKER")
    updates: dict[str, str] = {}
    if not parse_error:
        try:
            updates = planned_updates(data)
        except Exception as exc:
            rows.append(PlanRow("metadata application", "BLOCKER", str(exc), "Fix the target source structure before applying metadata."))
            blocker_count += 1

    applied = False
    if args.apply:
        if blocker_count:
            write_plan(rows, updates, apply_requested=True, applied=False)
            raise SystemExit("Refusing to apply metadata while blockers remain.")
        for rel, content in updates.items():
            (PKG / rel).write_text(content)
        applied = True

    write_plan(rows, updates, apply_requested=args.apply, applied=applied)
    print(f"Wrote {PLAN_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Metadata application status: {'APPLIED' if applied else 'DRY_RUN'}; blockers={blocker_count}")


if __name__ == "__main__":
    main()
