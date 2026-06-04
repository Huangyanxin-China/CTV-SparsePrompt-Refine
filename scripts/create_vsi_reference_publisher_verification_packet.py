#!/usr/bin/env python3
"""Create an author-facing publisher-record verification packet for references."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "manuscript_vsi_biomedical_data" / "references.bib"
MD_OUT = ROOT / "manuscript_vsi_biomedical_data" / "reference_publisher_verification_packet.md"
CSV_OUT = ROOT / "reports" / "vsi_reference_publisher_verification_packet_20260531.csv"

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
        value = value.replace("{", "").replace("}", "")
        fields[name] = " ".join(value.split())
    return fields


def normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.strip()


def missing_required(entry: dict[str, object]) -> list[str]:
    entry_type = str(entry["type"])
    fields = entry["fields"]
    assert isinstance(fields, dict)
    required = ["title", "author", "year"]
    if entry_type == "article":
        required.append("journal")
    elif entry_type in {"inproceedings", "incollection"}:
        required.append("booktitle")
    missing = [field for field in required if not fields.get(field)]
    if not any(fields.get(field) for field in ["doi", "url", "eprint"]):
        missing.append("doi/url/eprint")
    return missing


def identifier_failures(fields: dict[str, str]) -> list[str]:
    failures = []
    doi = normalize_doi(fields.get("doi", ""))
    eprint = fields.get("eprint", "").strip()
    archive = fields.get("archiveprefix", "").strip()
    if not any([doi, eprint, fields.get("url", "").strip()]):
        failures.append("missing DOI/arXiv/URL identifier")
    if doi and not DOI_RE.match(doi):
        failures.append("invalid DOI format")
    if eprint and not ARXIV_RE.match(eprint):
        failures.append("invalid arXiv eprint format")
    if eprint and archive.lower() != "arxiv":
        failures.append("arXiv eprint missing archivePrefix=arXiv")
    return failures


def resolver_for(fields: dict[str, str]) -> tuple[str, str]:
    doi = normalize_doi(fields.get("doi", ""))
    eprint = fields.get("eprint", "").strip()
    url = fields.get("url", "").strip()
    if doi:
        return doi, f"https://doi.org/{doi}"
    if eprint:
        return eprint, f"https://arxiv.org/abs/{eprint}"
    if url:
        return url, url
    return "", ""


def venue_for(entry_type: str, fields: dict[str, str]) -> str:
    if entry_type == "article":
        return fields.get("journal", "")
    if entry_type in {"inproceedings", "incollection"}:
        return fields.get("booktitle", "")
    return fields.get("archiveprefix", fields.get("howpublished", ""))


def manual_status(fields: dict[str, str], structural_failures: list[str], id_failures: list[str]) -> str:
    doi = normalize_doi(fields.get("doi", ""))
    eprint = fields.get("eprint", "").strip()
    author = fields.get("author", "")
    has_abbreviated_authors = re.search(r"\bothers\b", author, re.I) is not None
    accepted_check_recorded = bool(fields.get("acceptedversioncheck", "").strip())
    if structural_failures:
        return "STRUCTURAL_REPAIR_REQUIRED"
    if id_failures:
        return "IDENTIFIER_REPAIR_REQUIRED"
    if eprint and not doi and has_abbreviated_authors:
        return "ARXIV_ONLY_AND_AUTHOR_LIST_REVIEW_REQUIRED"
    if eprint and not doi:
        return "ARXIV_ONLY_REVIEW_REQUIRED"
    if has_abbreviated_authors:
        return "AUTHOR_LIST_AND_PUBLISHER_REVIEW_REQUIRED"
    if (doi.lower().startswith("10.48550/arxiv.") or eprint) and not accepted_check_recorded:
        return "ARXIV_DOI_VERSION_REVIEW_REQUIRED"
    return "PUBLISHER_RECORD_REVIEW_REQUIRED"


def required_checks(fields: dict[str, str], status: str) -> str:
    checks = [
        "title",
        "authors",
        "venue",
        "year",
        "volume/issue/pages-or-article-number",
        "identifier resolver",
    ]
    if "ARXIV" in status:
        checks.append("accepted-version search")
    if fields.get("acceptedversioncheck", "").strip():
        checks.append("verify recorded accepted-version check")
    if "AUTHOR_LIST" in status or re.search(r"\bothers\b", fields.get("author", ""), re.I):
        checks.append("expand abbreviated author list")
    if fields.get("doi", "").lower().startswith("10.48550/arxiv."):
        checks.append("confirm arXiv DOI/eprint match")
    return "; ".join(checks)


def row_for(entry: dict[str, object]) -> dict[str, str]:
    fields = entry["fields"]
    assert isinstance(fields, dict)
    entry_type = str(entry["type"])
    doi = normalize_doi(fields.get("doi", ""))
    eprint = fields.get("eprint", "").strip()
    source_id, resolver = resolver_for(fields)
    structural = missing_required(entry)
    id_failures = identifier_failures(fields)
    status = manual_status(fields, structural, id_failures)
    return {
        "key": str(entry["key"]),
        "type": entry_type,
        "year": fields.get("year", ""),
        "title": fields.get("title", ""),
        "authors": fields.get("author", ""),
        "venue": venue_for(entry_type, fields),
        "doi": doi,
        "eprint": eprint,
        "source_id": source_id,
        "resolver": resolver,
        "structural_status": "PASS_STRUCTURAL" if not structural else "STRUCTURAL_REPAIR_REQUIRED",
        "identifier_status": "PASS_IDENTIFIER" if not id_failures else "IDENTIFIER_REPAIR_REQUIRED",
        "manual_review_status": status,
        "required_checks": required_checks(fields, status),
        "notes": "; ".join(structural + id_failures),
    }


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "key",
        "type",
        "year",
        "title",
        "authors",
        "venue",
        "doi",
        "eprint",
        "source_id",
        "resolver",
        "structural_status",
        "identifier_status",
        "manual_review_status",
        "required_checks",
        "notes",
    ]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, str]]) -> None:
    structural_failures = [row for row in rows if row["structural_status"] != "PASS_STRUCTURAL"]
    identifier_failures_ = [row for row in rows if row["identifier_status"] != "PASS_IDENTIFIER"]
    doi_rows = [row for row in rows if row["doi"]]
    eprint_rows = [row for row in rows if row["eprint"]]
    arxiv_only = [row for row in rows if row["eprint"] and not row["doi"]]
    abbreviated = [row for row in rows if re.search(r"\bothers\b", row["authors"], re.I)]
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["manual_review_status"]] = status_counts.get(row["manual_review_status"], 0) + 1

    lines = [
        "# Reference Publisher Verification Packet",
        "",
        "This packet converts the local BibTeX and identifier audits into an author-facing checklist for final publisher-record verification. It is offline and reproducible; it does not claim that DOI, PubMed, publisher, or arXiv resolver pages were accessed during release.",
        "",
        "## Summary",
        "",
        "- Packet status: MANUAL_PUBLISHER_REVIEW_REQUIRED",
        f"- Entries queued: {len(rows)}",
        f"- Structural failures: {len(structural_failures)}",
        f"- Identifier failures: {len(identifier_failures_)}",
        f"- DOI entries: {len(doi_rows)}",
        f"- arXiv eprints: {len(eprint_rows)}",
        f"- arXiv-only entries: {len(arxiv_only)}",
        f"- Entries with abbreviated author lists: {len(abbreviated)}",
        "- Online resolver checks: NOT RUN BY RELEASE",
        "",
        "## Manual Review Status Counts",
        "",
        "| Status | Entries |",
        "| --- | ---: |",
    ]
    for status in sorted(status_counts):
        lines.append(f"| `{status}` | {status_counts[status]} |")

    lines.extend(
        [
            "",
            "## Required Manual Checks",
            "",
            "For each entry, verify the title, full author list and order, journal or proceedings name, year, volume, issue, pages or article number, and DOI/arXiv/URL resolver target against the authoritative publisher, DOI, PubMed, or arXiv record. For arXiv-only entries, check whether an accepted journal or conference version now exists before upload. For abbreviated `others` author lists, expand the author list if required by the journal or reference manager.",
            "",
            "## Verification Table",
            "",
            "| Key | Type | Year | Venue | Source ID | Resolver | Manual status | Required checks |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{escape_md(row['key'])}`",
                    escape_md(row["type"]),
                    escape_md(row["year"]),
                    escape_md(row["venue"] or "--"),
                    f"`{escape_md(row['source_id'] or '--')}`",
                    escape_md(row["resolver"] or "--"),
                    f"`{escape_md(row['manual_review_status'])}`",
                    escape_md(row["required_checks"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
        "## Evidence Inputs",
        "",
        "- `references.bib` is the authoritative local bibliography source.",
        "- `citation_metadata_audit.md` records structural BibTeX metadata completeness.",
        "- `reference_identifier_audit.md` records DOI/arXiv/URL syntax and resolver-link coverage.",
        "- `reference_online_metadata_audit.md` records the cached Crossref/arXiv/DataCite/PublisherURL metadata cross-check; it does not replace final author review.",
        "- `reference_publisher_signoff_form.md` records final human signoff after row-level publisher-record review.",
        "- `reports/vsi_reference_publisher_verification_packet_20260531.csv` contains the same queue in spreadsheet form for manual review tracking.",
        "- `reports/vsi_reference_publisher_signoff_20260531.csv` contains the machine-readable signoff audit.",
        "",
        "## Completion Rule",
        "",
        "This packet is complete as a review queue only. The submission remains blocked until the corresponding author or submitting author records every row in `reference_publisher_signoff_form.md` as checked against an authoritative publisher, DOI, PubMed, arXiv, proceedings, or open-access record and updates `references.bib` where needed.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    entries = parse_bibtex(BIB.read_text())
    rows = [row_for(entry) for entry in entries]
    write_csv(rows)
    write_markdown(rows)
    structural_failures = [row for row in rows if row["structural_status"] != "PASS_STRUCTURAL"]
    identifier_failures_ = [row for row in rows if row["identifier_status"] != "PASS_IDENTIFIER"]
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(
        "Reference publisher packet: "
        f"entries={len(rows)}; structural_failures={len(structural_failures)}; "
        f"identifier_failures={len(identifier_failures_)}"
    )


if __name__ == "__main__":
    main()
