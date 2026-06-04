#!/usr/bin/env python3
"""Audit BibTeX metadata completeness for the VSI manuscript package."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "manuscript_vsi_biomedical_data" / "references.bib"
CSV_OUT = ROOT / "reports" / "vsi_citation_metadata_audit_20260531.csv"
MD_OUT = ROOT / "manuscript_vsi_biomedical_data" / "citation_metadata_audit.md"


FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*[{\"](.*)", re.S)


def parse_bibtex(text: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    i = 0
    while True:
        at = text.find("@", i)
        if at == -1:
            break
        kind_end = text.find("{", at)
        if kind_end == -1:
            break
        entry_type = text[at + 1 : kind_end].strip().lower()
        depth = 0
        end = kind_end
        for pos in range(kind_end, len(text)):
            char = text[pos]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = pos
                    break
        body = text[kind_end + 1 : end]
        key, _, field_blob = body.partition(",")
        entries.append(
            {
                "type": entry_type,
                "key": key.strip(),
                "fields": parse_fields(field_blob),
            }
        )
        i = end + 1
    return entries


def parse_fields(blob: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = blob.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = FIELD_RE.match(line)
        if not match:
            idx += 1
            continue
        name = match.group(1).lower()
        value_part = match.group(2).strip()
        value_lines = [value_part]
        brace_balance = value_part.count("{") - value_part.count("}")
        quote_balance = value_part.count('"') % 2
        idx += 1
        while idx < len(lines) and (brace_balance > 0 or quote_balance):
            value_lines.append(lines[idx].strip())
            brace_balance += lines[idx].count("{") - lines[idx].count("}")
            quote_balance = (quote_balance + lines[idx].count('"')) % 2
            idx += 1
        value = " ".join(value_lines).rstrip(",").strip()
        value = value.strip("{}\"")
        fields[name] = " ".join(value.split())
    return fields


def missing_required(entry: dict[str, object]) -> list[str]:
    entry_type = str(entry["type"])
    fields = entry["fields"]
    assert isinstance(fields, dict)
    required = ["title", "author", "year"]
    if entry_type == "article":
        required.extend(["journal"])
    elif entry_type in {"inproceedings", "incollection"}:
        required.extend(["booktitle"])
    missing = [field for field in required if not fields.get(field)]
    if not any(fields.get(field) for field in ["doi", "url", "eprint"]):
        missing.append("doi/url/eprint")
    return missing


def metadata_notes(entry: dict[str, object]) -> list[str]:
    fields = entry["fields"]
    assert isinstance(fields, dict)
    notes = []
    author = fields.get("author", "")
    if re.search(r"\bothers\b", author, re.I):
        notes.append("author list abbreviated with 'others'")
    if fields.get("eprint") and not fields.get("doi"):
        notes.append("arXiv/eprint entry without DOI")
    if str(entry["type"]) == "article" and fields.get("doi") and not fields.get("pages"):
        notes.append("article has DOI but no pages/article number field")
    return notes


def row_for(entry: dict[str, object]) -> dict[str, str]:
    fields = entry["fields"]
    assert isinstance(fields, dict)
    missing = missing_required(entry)
    notes = metadata_notes(entry)
    source_id = fields.get("doi") or fields.get("eprint") or fields.get("url") or ""
    return {
        "key": str(entry["key"]),
        "type": str(entry["type"]),
        "year": fields.get("year", ""),
        "venue": fields.get("journal", fields.get("booktitle", fields.get("archiveprefix", ""))),
        "source_id": source_id,
        "structural_status": "PASS" if not missing else "FAIL",
        "missing_required": "; ".join(missing),
        "metadata_notes": "; ".join(notes),
    }


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "key",
        "type",
        "year",
        "venue",
        "source_id",
        "structural_status",
        "missing_required",
        "metadata_notes",
    ]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, str]]) -> None:
    total = len(rows)
    structural_failures = [row for row in rows if row["structural_status"] != "PASS"]
    notes = [row for row in rows if row["metadata_notes"]]
    lines = [
        "# Citation Metadata Audit",
        "",
        "This audit checks local BibTeX completeness for the Pattern Recognition VSI manuscript. It is a structural metadata audit, not a substitute for final publisher-record verification by the corresponding author.",
        "",
        "## Summary",
        "",
        f"- Total BibTeX entries: {total}",
        f"- Structural failures: {len(structural_failures)}",
        f"- Entries with final-review notes: {len(notes)}",
        "",
        "## Structural Checks",
        "",
        "Each entry must include title, author, year, an entry-type-specific venue field, and at least one DOI, URL, or eprint identifier.",
        "",
        "| Key | Type | Year | Source ID | Status | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        notes_text = row["metadata_notes"] or row["missing_required"] or ""
        source_id = row["source_id"].replace("|", "\\|")
        notes_text = notes_text.replace("|", "\\|")
        lines.append(
            f"| `{row['key']}` | {row['type']} | {row['year']} | `{source_id}` | {row['structural_status']} | {notes_text} |"
        )
    lines.extend(
        [
            "",
            "## Remaining Manual Citation Tasks",
            "",
            "- Replace abbreviated `others` author lists with complete publisher metadata before submission where required by journal style.",
            "- Confirm arXiv/eprint entries against the latest accepted versions and update DOI/journal fields if a peer-reviewed version is used.",
            "- Use `reference_identifier_audit.md` for offline DOI/arXiv/URL coverage and resolver links.",
            "- Run a final reference check in the submission system or reference manager immediately before upload.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    entries = parse_bibtex(BIB.read_text())
    rows = [row_for(entry) for entry in entries]
    write_csv(rows)
    write_markdown(rows)
    failures = [row for row in rows if row["structural_status"] != "PASS"]
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Entries: {len(rows)}; structural failures: {len(failures)}")
    if failures:
        for row in failures:
            print(f"FAIL {row['key']}: {row['missing_required']}")


if __name__ == "__main__":
    main()
