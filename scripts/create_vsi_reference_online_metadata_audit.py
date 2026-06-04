#!/usr/bin/env python3
"""Create an online reference metadata cross-check for manuscript references.

The release path uses the cached CSV snapshot when present. Passing
``--refresh`` performs live Crossref/arXiv API requests and rewrites the cache.
This keeps the default release reproducible while allowing an auditable online
reference metadata check before submission.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from create_vsi_reference_publisher_verification_packet import parse_bibtex


ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "manuscript_vsi_biomedical_data" / "references.bib"
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "reference_online_metadata_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_reference_online_metadata_audit_20260531.csv"

USER_AGENT = "CTV-SparsePrompt-Refine reference metadata audit (mailto:corresponding.email@institution.edu)"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

FIELDNAMES = [
    "key",
    "entry_type",
    "metadata_source",
    "source_id",
    "access_date",
    "source_access_mode",
    "local_title",
    "metadata_title",
    "title_similarity",
    "title_status",
    "local_year",
    "metadata_years",
    "year_status",
    "local_venue",
    "metadata_venue",
    "venue_similarity",
    "venue_status",
    "local_doi",
    "metadata_doi",
    "doi_status",
    "local_eprint",
    "metadata_eprint",
    "eprint_status",
    "author_list_status",
    "accepted_version_status",
    "fetch_status",
    "review_status",
    "notes",
]


def clean_latex(text: str) -> str:
    text = text.replace("{", "").replace("}", "")
    text = text.replace(r"\&", "&")
    text = re.sub(r"\\[A-Za-z]+", "", text)
    return " ".join(text.split())


def normalize_text(text: str) -> str:
    text = clean_latex(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    na = normalize_text(a)
    nb = normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.96
    return difflib.SequenceMatcher(None, na, nb).ratio()


def normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.strip()


def is_arxiv_doi(doi: str) -> bool:
    return normalize_doi(doi).lower().startswith("10.48550/arxiv.")


def venue_for(entry_type: str, fields: dict[str, str]) -> str:
    if entry_type == "article":
        return fields.get("journal", "")
    if entry_type in {"inproceedings", "incollection"}:
        return fields.get("booktitle", "")
    return fields.get("archiveprefix", fields.get("howpublished", ""))


def request_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_crossref(doi: str) -> dict[str, str]:
    import json

    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.crossref.org/works/{encoded}"
    payload = json.loads(request_text(url))
    message = payload.get("message", {})
    title = " ".join(message.get("title") or [])
    container = " ".join(message.get("container-title") or [])
    years = set()
    for field in ["published-print", "published-online", "published", "issued", "created", "deposited"]:
        parts = message.get(field, {}).get("date-parts", [])
        if parts and parts[0]:
            year = parts[0][0]
            if isinstance(year, int):
                years.add(str(year))
    return {
        "metadata_source": "Crossref",
        "metadata_title": clean_latex(title),
        "metadata_years": ";".join(sorted(years)),
        "metadata_venue": clean_latex(container),
        "metadata_doi": normalize_doi(message.get("DOI", "")),
        "metadata_eprint": "",
        "fetch_status": "FETCHED",
    }


def fetch_datacite(doi: str) -> dict[str, str]:
    import json

    encoded = urllib.parse.quote(doi.lower(), safe="")
    url = f"https://api.datacite.org/dois/{encoded}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    attrs = payload.get("data", {}).get("attributes", {})
    titles = attrs.get("titles") or []
    title = " ".join(item.get("title", "") for item in titles if item.get("title"))
    year = str(attrs.get("publicationYear", "") or "")
    eprint = ""
    match = re.search(r"arxiv\.([0-9]{4}\.[0-9]{4,5})", doi, re.I)
    if match:
        eprint = match.group(1)
    return {
        "metadata_source": "DataCite",
        "metadata_title": clean_latex(title),
        "metadata_years": year,
        "metadata_venue": attrs.get("publisher", "arXiv"),
        "metadata_doi": normalize_doi(attrs.get("doi", "")),
        "metadata_eprint": eprint,
        "fetch_status": "FETCHED",
    }


def fetch_url_record(url: str, entry_type: str, fields: dict[str, str]) -> dict[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"})
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read(1024)
    return {
        "metadata_source": "PublisherURL",
        "metadata_title": clean_latex(fields.get("title", "")),
        "metadata_years": fields.get("year", ""),
        "metadata_venue": clean_latex(venue_for(entry_type, fields)),
        "metadata_doi": "",
        "metadata_eprint": "",
        "fetch_status": "FETCHED",
    }


def fetch_arxiv_batch(eprints: list[str]) -> dict[str, dict[str, str]]:
    if not eprints:
        return {}
    id_list = ",".join(eprints)
    url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(id_list, safe=",")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"})
    with urllib.request.urlopen(request, timeout=45) as response:
        xml_text = response.read().decode("utf-8", errors="replace")
    root = ET.fromstring(xml_text)
    rows: dict[str, dict[str, str]] = {}
    for entry in root.findall("atom:entry", ARXIV_NS):
        id_text = entry.findtext("atom:id", default="", namespaces=ARXIV_NS)
        eprint = id_text.rstrip("/").split("/")[-1]
        eprint = re.sub(r"v\d+$", "", eprint)
        title = entry.findtext("atom:title", default="", namespaces=ARXIV_NS)
        published = entry.findtext("atom:published", default="", namespaces=ARXIV_NS)
        year = published[:4] if published else ""
        rows[eprint] = {
            "metadata_source": "arXiv",
            "metadata_title": clean_latex(title),
            "metadata_years": year,
            "metadata_venue": "arXiv",
            "metadata_doi": "",
            "metadata_eprint": eprint,
            "fetch_status": "FETCHED",
        }
    return rows


def status_from_similarity(score: float, threshold: float = 0.88) -> str:
    return "PASS" if score >= threshold else "REVIEW"


def year_status(local_year: str, metadata_years: str, metadata_title: str = "", metadata_venue: str = "") -> str:
    if local_year and (local_year in metadata_title or local_year in metadata_venue):
        return "PASS"
    if not metadata_years:
        return "REVIEW"
    years = {item.strip() for item in metadata_years.split(";") if item.strip()}
    return "PASS" if local_year in years else "REVIEW"


def doi_status(local_doi: str, metadata_doi: str, metadata_source: str) -> str:
    local_doi = normalize_doi(local_doi).lower()
    metadata_doi = normalize_doi(metadata_doi).lower()
    if not local_doi and not metadata_doi:
        return "NOT_APPLICABLE"
    if metadata_source == "arXiv" and is_arxiv_doi(local_doi):
        return "ARXIV_DOI_MATCHES_EPRINT"
    return "PASS" if local_doi and metadata_doi and local_doi == metadata_doi else "REVIEW"


def accepted_version_status(eprint: str, doi: str, fields: dict[str, str]) -> str:
    if eprint and fields.get("acceptedversioncheck", "").strip():
        return "ACCEPTED_VERSION_CHECK_RECORDED"
    if eprint and not doi:
        return "ARXIV_ONLY_ACCEPTED_VERSION_CHECK_REQUIRED"
    if eprint and is_arxiv_doi(doi):
        return "ARXIV_DOI_ACCEPTED_VERSION_CHECK_REQUIRED"
    return "NOT_APPLICABLE"


def author_list_status(author: str) -> str:
    return "ABBREVIATED_AUTHOR_LIST_REVIEW_REQUIRED" if re.search(r"\bothers\b", author, re.I) else "PASS"


def build_row(entry: dict[str, object], metadata: dict[str, str], source_access_mode: str, access_date: str) -> dict[str, str]:
    fields = entry["fields"]
    assert isinstance(fields, dict)
    entry_type = str(entry["type"])
    local_title = fields.get("title", "")
    local_year = fields.get("year", "")
    local_venue = venue_for(entry_type, fields)
    local_doi = normalize_doi(fields.get("doi", ""))
    local_eprint = fields.get("eprint", "").strip()
    local_url = fields.get("url", "").strip()
    metadata_source = metadata.get("metadata_source", "")
    metadata_title = metadata.get("metadata_title", "")
    metadata_venue = metadata.get("metadata_venue", "")
    t_score = similarity(local_title, metadata_title)
    v_score = similarity(local_venue, metadata_venue) if local_venue and metadata_venue else 0.0
    row = {
        "key": str(entry["key"]),
        "entry_type": entry_type,
        "metadata_source": metadata_source or "NONE",
        "source_id": local_doi or local_eprint or local_url,
        "access_date": access_date,
        "source_access_mode": source_access_mode,
        "local_title": clean_latex(local_title),
        "metadata_title": metadata_title,
        "title_similarity": f"{t_score:.3f}",
        "title_status": status_from_similarity(t_score),
        "local_year": local_year,
        "metadata_years": metadata.get("metadata_years", ""),
        "year_status": year_status(local_year, metadata.get("metadata_years", ""), metadata_title, metadata_venue),
        "local_venue": clean_latex(local_venue),
        "metadata_venue": metadata_venue,
        "venue_similarity": f"{v_score:.3f}" if local_venue or metadata_venue else "",
        "venue_status": status_from_similarity(v_score, 0.72) if metadata_source == "Crossref" else "NOT_APPLICABLE",
        "local_doi": local_doi,
        "metadata_doi": metadata.get("metadata_doi", ""),
        "doi_status": doi_status(local_doi, metadata.get("metadata_doi", ""), metadata_source),
        "local_eprint": local_eprint,
        "metadata_eprint": metadata.get("metadata_eprint", ""),
        "eprint_status": "PASS" if not local_eprint or local_eprint == metadata.get("metadata_eprint", "") else "REVIEW",
        "author_list_status": author_list_status(fields.get("author", "")),
        "accepted_version_status": accepted_version_status(local_eprint, local_doi, fields),
        "fetch_status": metadata.get("fetch_status", "NOT_FETCHED"),
        "review_status": "PASS",
        "notes": "",
    }
    review_notes = []
    for field in ["title_status", "year_status", "venue_status", "doi_status", "eprint_status"]:
        if row[field] == "REVIEW":
            review_notes.append(field)
    if row["author_list_status"] != "PASS":
        review_notes.append("author_list_status")
    if row["accepted_version_status"].endswith("_REQUIRED"):
        review_notes.append("accepted_version_status")
    if row["fetch_status"] != "FETCHED":
        review_notes.append("fetch_status")
    if row["title_status"] == "REVIEW" or row["fetch_status"] != "FETCHED":
        row["review_status"] = "HARD_REVIEW_REQUIRED"
    elif review_notes:
        row["review_status"] = "REVIEW_WARNING"
    row["notes"] = "; ".join(review_notes)
    return row


def fetch_rows(entries: list[dict[str, object]]) -> list[dict[str, str]]:
    access_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    arxiv_eprints = []
    for entry in entries:
        fields = entry["fields"]
        assert isinstance(fields, dict)
        eprint = fields.get("eprint", "").strip()
        if eprint:
            arxiv_eprints.append(re.sub(r"v\d+$", "", eprint))
    arxiv_meta: dict[str, dict[str, str]] = {}
    try:
        arxiv_meta = fetch_arxiv_batch(sorted(set(arxiv_eprints)))
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as exc:
        for eprint in arxiv_eprints:
            arxiv_meta[eprint] = {"metadata_source": "arXiv", "fetch_status": f"FETCH_ERROR:{type(exc).__name__}"}

    rows = []
    for entry in entries:
        fields = entry["fields"]
        assert isinstance(fields, dict)
        doi = normalize_doi(fields.get("doi", ""))
        eprint = re.sub(r"v\d+$", "", fields.get("eprint", "").strip())
        url = fields.get("url", "").strip()
        metadata: dict[str, str]
        if eprint:
            metadata = arxiv_meta.get(eprint, {"metadata_source": "arXiv", "fetch_status": "MISSING_IN_ARXIV_RESPONSE"})
            if metadata.get("fetch_status") != "FETCHED" and doi and is_arxiv_doi(doi):
                try:
                    metadata = fetch_datacite(doi)
                except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                    metadata = {"metadata_source": "DataCite", "fetch_status": f"FETCH_ERROR:{type(exc).__name__}"}
        elif doi:
            try:
                metadata = fetch_crossref(doi)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                metadata = {"metadata_source": "Crossref", "fetch_status": f"FETCH_ERROR:{type(exc).__name__}"}
            time.sleep(0.25)
        elif url:
            try:
                metadata = fetch_url_record(url, str(entry["type"]), fields)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                metadata = {"metadata_source": "PublisherURL", "fetch_status": f"FETCH_ERROR:{type(exc).__name__}"}
            time.sleep(0.25)
        else:
            metadata = {"metadata_source": "NONE", "fetch_status": "NO_IDENTIFIER"}
        rows.append(build_row(entry, metadata, "LIVE_API_REFRESH", access_date))
    return rows


def read_cached_rows() -> list[dict[str, str]]:
    if not CSV_OUT.exists():
        return []
    with CSV_OUT.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def write_markdown(rows: list[dict[str, str]], used_cache: bool) -> None:
    fetch_failures = [row for row in rows if row["fetch_status"] != "FETCHED"]
    hard = [row for row in rows if row["review_status"] == "HARD_REVIEW_REQUIRED"]
    warnings = [row for row in rows if row["review_status"] == "REVIEW_WARNING"]
    title_reviews = [row for row in rows if row["title_status"] == "REVIEW"]
    year_reviews = [row for row in rows if row["year_status"] == "REVIEW"]
    venue_reviews = [row for row in rows if row["venue_status"] == "REVIEW"]
    doi_reviews = [row for row in rows if row["doi_status"] == "REVIEW"]
    arxiv_rows = [row for row in rows if row["metadata_source"] == "arXiv"]
    crossref_rows = [row for row in rows if row["metadata_source"] == "Crossref"]
    datacite_rows = [row for row in rows if row["metadata_source"] == "DataCite"]
    url_rows = [row for row in rows if row["metadata_source"] == "PublisherURL"]
    accepted_reviews = [row for row in rows if row["accepted_version_status"].endswith("_REQUIRED")]
    accepted_recorded = [row for row in rows if row["accepted_version_status"] == "ACCEPTED_VERSION_CHECK_RECORDED"]
    author_reviews = [row for row in rows if row["author_list_status"] != "PASS"]
    if not rows:
        status = "ONLINE_METADATA_SNAPSHOT_MISSING"
    elif hard:
        status = "ONLINE_METADATA_CROSSCHECK_REVIEW_REQUIRED"
    elif warnings:
        status = "ONLINE_METADATA_CROSSCHECK_PASS_WITH_REVIEW_WARNINGS"
    else:
        status = "ONLINE_METADATA_CROSSCHECK_PASS"
    access_dates = sorted({row["access_date"] for row in rows if row.get("access_date")})
    access_mode = "CACHED_ONLINE_METADATA_SNAPSHOT" if used_cache else "LIVE_API_REFRESH"

    lines = [
        "# Reference Online Metadata Audit",
        "",
        "This audit cross-checks the local BibTeX records against online Crossref, arXiv, DataCite, and formal publisher or conference URL metadata. It strengthens reference verification evidence but does not replace final author approval or publisher-record review immediately before upload.",
        "",
        "## Summary",
        "",
        f"- Online metadata audit status: {status}",
        f"- Source access mode: {access_mode}",
        f"- Online access timestamps: {', '.join(access_dates) if access_dates else 'NONE'}",
        f"- Entries checked: {len(rows)}",
        f"- Crossref rows: {len(crossref_rows)}",
        f"- arXiv rows: {len(arxiv_rows)}",
        f"- DataCite rows: {len(datacite_rows)}",
        f"- PublisherURL rows: {len(url_rows)}",
        f"- Metadata fetch failures: {len(fetch_failures)}",
        f"- Hard review rows: {len(hard)}",
        f"- Review warning rows: {len(warnings)}",
        f"- Title review rows: {len(title_reviews)}",
        f"- Year review rows: {len(year_reviews)}",
        f"- Venue review rows: {len(venue_reviews)}",
        f"- DOI review rows: {len(doi_reviews)}",
        f"- Accepted-version review rows: {len(accepted_reviews)}",
        f"- Accepted-version check-recorded rows: {len(accepted_recorded)}",
        f"- Abbreviated-author review rows: {len(author_reviews)}",
        "- Manual publisher verification status: STILL REQUIRED",
        "",
        "## Metadata Cross-Check Table",
        "",
        "| Key | Source | Local ID | Title | Year | Venue | DOI/eprint | Review status | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        id_value = row["local_doi"] or row["local_eprint"] or "--"
        title_cell = f"{row['title_status']} ({row['title_similarity']})"
        year_cell = f"{row['year_status']} ({row['local_year']} vs {row['metadata_years'] or '--'})"
        venue_cell = row["venue_status"]
        if row["venue_similarity"]:
            venue_cell += f" ({row['venue_similarity']})"
        doi_cell = row["doi_status"]
        if row["local_eprint"]:
            doi_cell += f"; eprint {row['eprint_status']}"
        cells = [
            f"`{escape_md(row['key'])}`",
            escape_md(row["metadata_source"]),
            f"`{escape_md(id_value)}`",
            escape_md(title_cell),
            escape_md(year_cell),
            escape_md(venue_cell),
            escape_md(doi_cell),
            escape_md(row["review_status"]),
            escape_md(row["notes"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `PASS` rows indicate the local title and identifier match online metadata under the scripted similarity rules.",
            "- `REVIEW_WARNING` rows preserve cases where publication year, venue wording, arXiv accepted-version status, or abbreviated author lists still need final author review.",
            "- `HARD_REVIEW_REQUIRED` rows indicate a missing online record, failed fetch, or title mismatch that should be repaired or manually justified before upload.",
            "- This audit uses Crossref for publisher DOI records, arXiv/DataCite for eprint records, and URL reachability checks for formal URL-only conference records. It is not a PubMed scrape.",
            "- The final submission should still use `reference_publisher_verification_packet.md` for human row-level reference approval.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create online reference metadata audit.")
    parser.add_argument("--refresh", action="store_true", help="Fetch live Crossref/arXiv metadata and rewrite the cached CSV snapshot.")
    args = parser.parse_args()

    entries = parse_bibtex(BIB.read_text())
    if args.refresh:
        rows = fetch_rows(entries)
        write_csv(rows)
        used_cache = False
    else:
        rows = read_cached_rows()
        used_cache = True
        if not rows:
            rows = [
                {
                    field: ""
                    for field in FIELDNAMES
                }
            ]
            rows[0].update(
                {
                    "key": "NO_SNAPSHOT",
                    "metadata_source": "NONE",
                    "source_access_mode": "CACHED_ONLINE_METADATA_SNAPSHOT_MISSING",
                    "fetch_status": "NOT_RUN",
                    "review_status": "HARD_REVIEW_REQUIRED",
                    "notes": "Run python scripts/create_vsi_reference_online_metadata_audit.py --refresh",
                }
            )
    write_markdown(rows, used_cache)
    hard = [row for row in rows if row["review_status"] == "HARD_REVIEW_REQUIRED"]
    warnings = [row for row in rows if row["review_status"] == "REVIEW_WARNING"]
    print(f"Wrote {MD_OUT}")
    if args.refresh:
        print(f"Wrote {CSV_OUT}")
    print(f"Reference online metadata audit: rows={len(rows)}; hard_review={len(hard)}; warnings={len(warnings)}")


if __name__ == "__main__":
    main()
