#!/usr/bin/env python3
"""Audit DOI, arXiv, and URL identifiers in the VSI BibTeX file."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "manuscript_vsi_biomedical_data" / "references.bib"
CSV_OUT = ROOT / "reports" / "vsi_reference_identifier_audit_20260531.csv"
MD_OUT = ROOT / "manuscript_vsi_biomedical_data" / "reference_identifier_audit.md"

FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*[{\"](.*)", re.S)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
ARXIV_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.I)


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
        entries.append({"type": entry_type, "key": key.strip(), "fields": parse_fields(field_blob)})
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


def normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.strip()


def resolver_for(fields: dict[str, str]) -> tuple[str, str]:
    doi = normalize_doi(fields.get("doi", ""))
    eprint = fields.get("eprint", "").strip()
    url = fields.get("url", "").strip()
    if doi:
        return "DOI", f"https://doi.org/{doi}"
    if eprint:
        return "arXiv", f"https://arxiv.org/abs/{eprint}"
    if url:
        return "URL", url
    return "missing", ""


def row_for(entry: dict[str, object]) -> dict[str, str]:
    fields = entry["fields"]
    assert isinstance(fields, dict)
    key = str(entry["key"])
    doi = normalize_doi(fields.get("doi", ""))
    eprint = fields.get("eprint", "").strip()
    archive = fields.get("archiveprefix", "").strip()
    url = fields.get("url", "").strip()
    kind, resolver = resolver_for(fields)

    failures = []
    warnings = []
    if not any([doi, eprint, url]):
        failures.append("missing DOI/arXiv/URL identifier")
    if doi and not DOI_RE.match(doi):
        failures.append("invalid DOI format")
    if eprint and not ARXIV_RE.match(eprint):
        failures.append("invalid arXiv eprint format")
    if eprint and archive.lower() != "arxiv":
        failures.append("arXiv eprint missing archivePrefix=arXiv")
    if eprint and not doi:
        warnings.append("arXiv-only entry; check for accepted version before submission")
    if re.search(r"\bothers\b", fields.get("author", ""), re.I):
        warnings.append("author list abbreviated with 'others'")
    if doi.lower().startswith("10.48550/arxiv.") and eprint:
        doi_suffix = doi.split("arXiv.", 1)[-1].lower()
        if doi_suffix != eprint.lower():
            warnings.append("arXiv DOI suffix does not exactly match eprint")

    return {
        "key": key,
        "type": str(entry["type"]),
        "year": fields.get("year", ""),
        "identifier_kind": kind,
        "doi": doi,
        "eprint": eprint,
        "resolver": resolver,
        "identifier_status": "PASS" if not failures else "FAIL",
        "failures": "; ".join(failures),
        "warnings": "; ".join(warnings),
    }


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "key",
        "type",
        "year",
        "identifier_kind",
        "doi",
        "eprint",
        "resolver",
        "identifier_status",
        "failures",
        "warnings",
    ]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, str]]) -> None:
    failures = [row for row in rows if row["identifier_status"] != "PASS"]
    warning_rows = [row for row in rows if row["warnings"]]
    doi_rows = [row for row in rows if row["doi"]]
    eprint_rows = [row for row in rows if row["eprint"]]
    arxiv_only_rows = [row for row in rows if row["eprint"] and not row["doi"]]
    lines = [
        "# Reference Identifier Audit",
        "",
        "This audit validates local DOI, arXiv, and URL identifier coverage for the manuscript bibliography. It is offline and reproducible; it does not replace final publisher-record verification.",
        "",
        "## Summary",
        "",
        f"- Total BibTeX entries: {len(rows)}",
        f"- DOI identifiers: {len(doi_rows)}",
        f"- arXiv eprints: {len(eprint_rows)}",
        f"- arXiv-only entries: {len(arxiv_only_rows)}",
        f"- Identifier failures: {len(failures)}",
        f"- Entries with manual-review warnings: {len(warning_rows)}",
        "- Online resolver checks: NOT RUN BY RELEASE",
        "",
        "## Identifier Checks",
        "",
        "| Key | Kind | DOI | arXiv | Resolver | Status | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        doi = row["doi"] or "--"
        eprint = row["eprint"] or "--"
        resolver = row["resolver"] or "--"
        notes = row["failures"] or row["warnings"] or ""
        notes = notes.replace("|", "\\|")
        lines.append(
            f"| `{row['key']}` | {row['identifier_kind']} | `{doi}` | `{eprint}` | {resolver} | {row['identifier_status']} | {notes} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `PASS` means the local identifier is present and syntactically valid.",
            "- arXiv-only entries and abbreviated author lists still require manual publisher-record review before upload.",
            "- Optional online spot checks can be run with DOI or arXiv resolver URLs listed above, but release remains offline to avoid network-dependent reproducibility failures.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    entries = parse_bibtex(BIB.read_text())
    rows = [row_for(entry) for entry in entries]
    write_csv(rows)
    write_markdown(rows)
    failures = [row for row in rows if row["identifier_status"] != "PASS"]
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Entries: {len(rows)}; identifier failures: {len(failures)}")
    if failures:
        for row in failures:
            print(f"FAIL {row['key']}: {row['failures']}")


if __name__ == "__main__":
    main()
