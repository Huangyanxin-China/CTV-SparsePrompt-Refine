#!/usr/bin/env python3
"""Audit package-level consistency for stable manuscript facts."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "package_consistency_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_package_consistency_audit_20260601.csv"


@dataclass
class Row:
    check: str
    status: str
    observed: str
    required_action: str


def read_pkg(rel: str) -> str:
    path = PKG / rel
    return path.read_text(errors="replace") if path.exists() else ""


def read_root(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(errors="replace") if path.exists() else ""


def first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def add(rows: list[Row], check: str, ok: bool, observed: str, required_action: str = "No action.") -> None:
    rows.append(Row(check, status(ok), observed, required_action if not ok else "No action."))


def count_highlights() -> int:
    return len(re.findall(r"^\\item\s+", read_pkg("highlights.tex"), flags=re.MULTILINE))


def scan_text(paths: list[tuple[str, str]], pattern: str) -> list[str]:
    regex = re.compile(pattern)
    hits: list[str] = []
    for rel, text in paths:
        if regex.search(text):
            hits.append(rel)
    return hits


def main() -> None:
    highlights = count_highlights()
    pdf_render = read_pkg("pdf_render_audit.md")
    prescreen = read_pkg("rendered_pdf_visual_prescreen.md")
    source_layout = read_pkg("source_layout_audit.md")
    blocker = read_pkg("submission_blocker_audit.md")
    quickstart = read_pkg("human_completion_quickstart.md")
    handoff = read_pkg("final_submission_handoff.md")
    upload_index = read_pkg("editorial_manager_upload_index.md")
    traceability = read_pkg("submission_requirements_traceability.md")
    source_evidence = read_pkg("source_evidence_manifest.md")
    readme = read_pkg("README.md")
    checklist = read_pkg("submission_checklist.md")
    metadata = read_pkg("submission_metadata_template.yaml")
    cover_letter = read_pkg("cover_letter.txt")
    peer_risk = read_pkg("peer_review_risk_audit.md")
    closure = read_root("reports/vsi_paper_closure_status_20260531.md")

    pdf_pages = first_match(r"^- Rendered page count:\s*(\d+)", pdf_render)
    prescreen_pages = first_match(r"^- Rendered page count:\s*(\d+)", prescreen)
    source_estimate = first_match(r"^- Estimated page count:\s*([0-9.]+)", source_layout)
    blocker_count = first_match(r"^- Outstanding blocker count:\s*(\d+)", blocker)
    quickstart_blockers = first_match(r"^- Outstanding blocker count:\s*(\d+)", quickstart)
    handoff_blockers = first_match(r"^- Blocking handoff gates:\s*(\d+)", handoff)
    article_type = first_match(r"^article_type:\s*[\"']?([^\"'\n]+)", metadata)

    rows: list[Row] = []
    add(rows, "Current highlight count available", highlights > 0, f"{highlights} highlights", "Restore highlights.tex.")
    add(rows, "Current rendered PDF page count available", bool(pdf_pages), pdf_pages or "missing", "Regenerate pdf_render_audit.md.")
    add(
        rows,
        "Rendered PDF audits agree on page count",
        bool(pdf_pages) and pdf_pages == prescreen_pages,
        f"pdf_render={pdf_pages or 'missing'}; prescreen={prescreen_pages or 'missing'}",
        "Rerun pdf-render-compile and pdf-prescreen.",
    )
    add(rows, "Current source page estimate available", bool(source_estimate), source_estimate or "missing", "Regenerate source_layout_audit.md.")
    add(rows, "Current blocker count available", bool(blocker_count), blocker_count or "missing", "Regenerate submission_blocker_audit.md.")
    add(
        rows,
        "Quickstart blocker count matches blocker audit",
        bool(blocker_count) and blocker_count == quickstart_blockers,
        f"blocker={blocker_count or 'missing'}; quickstart={quickstart_blockers or 'missing'}",
        "Regenerate human_completion_quickstart.md.",
    )
    add(
        rows,
        "Final handoff blocker count matches blocker audit",
        bool(blocker_count) and blocker_count == handoff_blockers,
        f"blocker={blocker_count or 'missing'}; handoff={handoff_blockers or 'missing'}",
        "Regenerate final_submission_handoff.md.",
    )
    add(
        rows,
        "Editorial upload index records current highlight count",
        f"{highlights} highlights" in upload_index,
        f"{highlights} highlights expected",
        "Update editorial_manager_upload_index.md.",
    )
    add(
        rows,
        "Peer-review risk audit records current highlight count",
        f"{highlights} compliant highlights" in peer_risk,
        f"{highlights} compliant highlights expected",
        "Update peer_review_risk_audit.md.",
    )
    add(
        rows,
        "Closure status records current highlight count",
        f"{highlights} highlights under 85 characters" in closure,
        f"{highlights} highlights expected",
        "Update reports/vsi_paper_closure_status_20260531.md.",
    )
    add(
        rows,
        "README records current source estimate",
        bool(source_estimate) and f"estimates {source_estimate} pages" in readme,
        f"source estimate={source_estimate or 'missing'}",
        "Update README.md.",
    )
    add(
        rows,
        "Submission checklist records current source estimate",
        bool(source_estimate) and f"estimates {source_estimate} pages" in checklist,
        f"source estimate={source_estimate or 'missing'}",
        "Update submission_checklist.md.",
    )
    add(
        rows,
        "README records current rendered PDF page count",
        bool(pdf_pages) and f"renders to {pdf_pages} pages" in readme,
        f"rendered pages={pdf_pages or 'missing'}",
        "Update README.md.",
    )
    add(
        rows,
        "Traceability records current rendered PDF page count",
        bool(pdf_pages) and f"{pdf_pages}-page rendered PDF evidence" in traceability and f"{pdf_pages}-page count" in traceability,
        f"rendered pages={pdf_pages or 'missing'}",
        "Update submission_requirements_traceability.md.",
    )
    add(
        rows,
        "Source evidence manifest records current rendered PDF page count",
        bool(pdf_pages) and f"rendered {pdf_pages}-page count" in source_evidence,
        f"rendered pages={pdf_pages or 'missing'}",
        "Update source_evidence_manifest.md.",
    )
    add(
        rows,
        "Quickstart records current rendered PDF page count",
        bool(pdf_pages) and f"PDF page count: {pdf_pages}" in quickstart,
        f"rendered pages={pdf_pages or 'missing'}",
        "Regenerate human_completion_quickstart.md.",
    )
    add(
        rows,
        "Article type consistent across metadata, cover letter, and upload index",
        article_type == "VSI: PR_Biomedical Data" and article_type in cover_letter and article_type in upload_index,
        f"article_type={article_type or 'missing'}",
        "Restore VSI: PR_Biomedical Data in metadata, cover letter, and upload index.",
    )

    docs_to_scan = [
        ("README.md", readme),
        ("submission_checklist.md", checklist),
        ("submission_requirements_traceability.md", traceability),
        ("source_evidence_manifest.md", source_evidence),
        ("editorial_manager_upload_index.md", upload_index),
        ("peer_review_risk_audit.md", peer_risk),
        ("human_completion_quickstart.md", quickstart),
        ("final_submission_handoff.md", handoff),
        ("reports/vsi_paper_closure_status_20260531.md", closure),
    ]
    stale_highlight_hits = scan_text(docs_to_scan, r"\b4 (?:compliant )?highlights\b") if highlights != 4 else []
    stale_source_hits = scan_text(docs_to_scan, r"\b24\.4 pages\b") if source_estimate != "24.4" else []
    stale_pdf_hits = scan_text(docs_to_scan, r"\b21(?:-page| pages)\b") if pdf_pages != "21" else []
    add(
        rows,
        "Stale 4-highlight claims absent",
        not stale_highlight_hits,
        ", ".join(stale_highlight_hits) if stale_highlight_hits else "none",
        "Update stale highlight-count prose.",
    )
    add(
        rows,
        "Stale 24.4-page source-estimate claims absent",
        not stale_source_hits,
        ", ".join(stale_source_hits) if stale_source_hits else "none",
        "Update stale source-estimate prose.",
    )
    add(
        rows,
        "Stale 21-page rendered PDF claims absent",
        not stale_pdf_hits,
        ", ".join(stale_pdf_hits) if stale_pdf_hits else "none",
        "Update stale rendered-page-count prose.",
    )

    failing = [row for row in rows if row.status == "FAIL"]
    audit_status = "PASS" if not failing else "FAIL"

    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "observed", "required_action"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)

    md_lines = [
        "# Package Consistency Audit",
        "",
        "This audit checks that stable package facts have not drifted across static handoff and traceability files. It does not replace author metadata, ethics, funding, reference, clinical-overlay, or final PDF signoff.",
        "",
        "## Summary",
        "",
        f"- Package consistency status: {audit_status}",
        f"- Failing checks: {len(failing)}",
        f"- Current highlight count: {highlights}",
        f"- Current source-level page estimate: {source_estimate or 'missing'}",
        f"- Current rendered PDF page count: {pdf_pages or 'missing'}",
        f"- Current outstanding blocker count: {blocker_count or 'missing'}",
        "",
        "## Checks",
        "",
        "| Check | Status | Observed | Required action |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        md_lines.append(f"| {row.check} | {row.status} | {row.observed} | {row.required_action} |")

    md_lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- PASS means the checked static files reflect the current generated facts for highlight count, rendered PDF page count, source estimate, blocker count, and article type.",
            "- This audit can pass while the package remains not ready for upload because real author metadata and manual signoffs are separate blockers.",
        ]
    )
    MD_OUT.write_text("\n".join(md_lines) + "\n")

    print(f"Package consistency status: {audit_status}; failing={len(failing)}")
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")


if __name__ == "__main__":
    main()
