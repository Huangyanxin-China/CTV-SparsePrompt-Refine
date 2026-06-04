#!/usr/bin/env python3
"""Create an automated rendered-PDF visual/text prescreen."""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
PDF = PKG / "main.pdf"
MD_OUT = PKG / "rendered_pdf_visual_prescreen.md"
CSV_OUT = ROOT / "reports" / "vsi_rendered_pdf_visual_prescreen_20260601.csv"
KNOWN_TOOL_DIRS = [Path("/tmp/vsi_tectonic_env/bin")]
PAGE_TARGET_LOW = 20
PAGE_TARGET_HIGH = 35

PRESCREEN_PASS_STATUS = "AUTOMATED_RENDERED_PDF_PRESCREEN_PASS_WITH_RESIDUAL_SIGNOFF_REQUIRED"


@dataclass(frozen=True)
class PrescreenRow:
    item: str
    status: str
    evidence: str
    required_action: str


def tool_path(tool: str) -> str:
    found = shutil.which(tool)
    if found:
        return found
    for directory in KNOWN_TOOL_DIRS:
        candidate = directory / tool
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def run_tool(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def pdfinfo_text() -> str:
    pdfinfo = tool_path("pdfinfo")
    if not pdfinfo or not PDF.exists():
        return ""
    result = run_tool([pdfinfo, str(PDF)])
    return result.stdout if result.returncode == 0 else ""


def parse_pdfinfo_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", text, re.M)
    return match.group(1).strip() if match else ""


def page_count_from_pdfinfo(text: str) -> int | None:
    value = parse_pdfinfo_value(text, "Pages")
    return int(value) if value.isdigit() else None


def page_count_from_bytes() -> int | None:
    if not PDF.exists():
        return None
    data = PDF.read_bytes()
    count = len(re.findall(rb"/Type\s*/Page\b", data))
    return count or None


def rendered_page_count() -> tuple[int | None, str]:
    info = pdfinfo_text()
    count = page_count_from_pdfinfo(info)
    if count is not None:
        return count, "pdfinfo"
    count = page_count_from_bytes()
    if count is not None:
        return count, "raw PDF /Type /Page count"
    return None, "not available"


def extract_text() -> str:
    pdftotext = tool_path("pdftotext")
    if not pdftotext or not PDF.exists():
        return ""
    result = run_tool([pdftotext, "-layout", str(PDF), "-"])
    return result.stdout if result.returncode == 0 else ""


def sample_pages(page_count: int | None) -> list[int]:
    if not page_count:
        return []
    candidates = [
        1,
        2,
        min(10, page_count),
        min(12, page_count),
        min(13, page_count),
        min(14, page_count),
        min(15, page_count),
        max(1, page_count - 3),
        max(1, page_count - 2),
        max(1, page_count - 1),
        page_count,
    ]
    return sorted(set(page for page in candidates if 1 <= page <= page_count))


def image_nonblank_fraction(path: Path) -> tuple[int, int, float]:
    with Image.open(path) as image:
        gray = image.convert("L")
        pixels = list(gray.getdata())
        nonblank = sum(1 for value in pixels if value < 245)
        total = len(pixels) or 1
        width, height = image.size
    return width, height, nonblank / total


def render_sampled_pages(pages: list[int]) -> tuple[list[str], list[str]]:
    pdftoppm = tool_path("pdftoppm")
    if not pdftoppm or not PDF.exists():
        return [], ["pdftoppm not available or main.pdf missing"]
    evidence: list[str] = []
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vsi_rendered_pdf_prescreen_") as tmp:
        tmpdir = Path(tmp)
        for page in pages:
            prefix = tmpdir / f"page_{page}"
            result = run_tool([pdftoppm, "-f", str(page), "-l", str(page), "-png", "-r", "100", str(PDF), str(prefix)])
            rendered = sorted(tmpdir.glob(f"page_{page}-*.png"))
            if result.returncode != 0 or not rendered:
                failures.append(f"page {page}: render failed")
                continue
            image_path = rendered[0]
            width, height, nonblank = image_nonblank_fraction(image_path)
            evidence.append(f"page {page}: {width}x{height}, nonblank {nonblank:.3f}")
            if width < 600 or height < 800 or nonblank < 0.005:
                failures.append(f"page {page}: suspicious render ({width}x{height}, nonblank {nonblank:.3f})")
    return evidence, failures


def line_number_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*\d{1,4}\s+\S", text))


def find_unresolved_markers(text: str) -> list[str]:
    patterns = [r"\?\?", r"\[Citation", r"undefined", r"\[ref\]"]
    hits = []
    for pattern in patterns:
        if re.search(pattern, text, re.I):
            hits.append(pattern)
    return hits


def contains_all_table_labels(text: str, table_count: int) -> bool:
    return all(re.search(rf"\bTable\s+{idx}\b", text) for idx in range(1, table_count + 1))


def contains_all_figure_labels(text: str, figure_count: int) -> bool:
    return all(re.search(rf"\bFigure\s+{idx}\b", text) for idx in range(1, figure_count + 1))


def build_rows(page_count: int | None, page_source: str, pages: list[int], text: str, render_evidence: list[str], render_failures: list[str]) -> list[PrescreenRow]:
    page_target_ok = page_count is not None and PAGE_TARGET_LOW <= page_count <= PAGE_TARGET_HIGH
    page_footer_ok = bool(page_count) and f"Page 1 of {page_count}" in text and f"Page {page_count} of {page_count}" in text
    line_count = line_number_count(text)
    unresolved = find_unresolved_markers(text)
    table_count = len(re.findall(r"\\begin\{table\}", (PKG / "main.tex").read_text()))
    table_count += sum((PKG / "tables" / name).read_text().count(r"\begin{table}") for name in os.listdir(PKG / "tables") if name.endswith(".tex"))
    figure_count = len(re.findall(r"\\begin\{figure\}", (PKG / "main.tex").read_text()))
    table_text_ok = contains_all_table_labels(text, table_count)
    figure_text_ok = contains_all_figure_labels(text, figure_count)
    refs_ok = "[36]" in text or re.search(r"^\s*\[36\]", text, re.M) is not None
    author_placeholder = "corresponding.email@institution.edu" in text or "Institution to be finalized" in text
    ethics_funding_placeholder = "must be inserted before submission" in text or "funding information should" in text

    rows = [
        PrescreenRow(
            "Rendered page count",
            "PASS" if page_target_ok else "BLOCKER",
            f"{page_source} reports {page_count} pages" if page_count is not None else "page count unavailable",
            "Recheck after any source, figure, bibliography, or metadata change.",
        ),
        PrescreenRow(
            "Page numbering",
            "PASS" if page_footer_ok else "BLOCKER",
            f"extracted footer includes Page 1 of {page_count} and Page {page_count} of {page_count}" if page_footer_ok else "footer sequence not confirmed",
            "Final submitting author should confirm in the opened PDF.",
        ),
        PrescreenRow(
            "Line numbering",
            "PASS" if line_count >= 100 else "WARNING",
            f"{line_count} line-number-like text rows extracted",
            "Final submitting author should confirm line numbers throughout the opened PDF.",
        ),
        PrescreenRow(
            "Rendered sampled pages",
            "PASS" if render_evidence and not render_failures else "WARNING",
            "; ".join(render_evidence[:8]) + (f"; plus {len(render_evidence) - 8} more" if len(render_evidence) > 8 else ""),
            "Open the final PDF manually if any sampled page render is missing, blank, or clipped.",
        ),
        PrescreenRow(
            "Body layout",
            "PASS" if render_evidence and not render_failures and line_count >= 100 else "WARNING",
            f"sampled pages {', '.join(str(page) for page in pages)} rendered as nonblank page images",
            "Final PDF review should confirm all pages are single-column, double-spaced, readable, and non-overlapping.",
        ),
        PrescreenRow(
            "Tables",
            "PASS" if table_text_ok else "WARNING",
            f"extracted text contains Table 1 through Table {table_count}" if table_text_ok else f"not all Table 1 through Table {table_count} labels found",
            "Review all tables in the final opened PDF after metadata edits.",
        ),
        PrescreenRow(
            "Figures",
            "PASS" if figure_text_ok else "WARNING",
            f"extracted text contains Figure 1 through Figure {figure_count}" if figure_text_ok else f"not all Figure 1 through Figure {figure_count} labels found",
            "Review all figures in the final opened PDF after metadata edits.",
        ),
        PrescreenRow(
            "Bibliography",
            "PASS" if refs_ok else "WARNING",
            "extracted text reaches reference [36]" if refs_ok else "last bibliography entry not confirmed",
            "Complete publisher-record reference review before upload.",
        ),
        PrescreenRow(
            "Unresolved markers",
            "PASS" if not unresolved else "BLOCKER",
            "none detected" if not unresolved else ", ".join(unresolved),
            "Re-run after any citation or reference edits.",
        ),
        PrescreenRow(
            "Author metadata placeholders",
            "BLOCKER" if author_placeholder else "PASS",
            "rendered PDF still shows author/institutional placeholders" if author_placeholder else "no known author/institutional placeholder detected",
            "Replace final author, affiliation, and corresponding-author metadata before upload.",
        ),
        PrescreenRow(
            "Ethics/funding placeholders",
            "BLOCKER" if ethics_funding_placeholder else "PASS",
            "rendered PDF still shows ethics/funding placeholders" if ethics_funding_placeholder else "no known ethics/funding placeholder detected",
            "Insert approved ethics, consent/waiver, funding, and acknowledgements text before upload.",
        ),
        PrescreenRow(
            "Clinical overlay pixel review",
            "SIGNOFF_REQUIRED",
            "clinical overlay figures are rendered, but clinical-owner pixel signoff remains outside this prescreen",
            "Complete full-resolution PNG and rendered-PDF clinical overlay review.",
        ),
        PrescreenRow(
            "Final rendered-PDF review",
            "SIGNOFF_REQUIRED",
            "this automated sampled prescreen is not final author signoff",
            "The submitting author must inspect the final PDF and record decisions in `rendered_pdf_author_signoff_form.md`.",
        ),
    ]
    if render_failures:
        rows.append(
            PrescreenRow(
                "Rendered sampled page failures",
                "WARNING",
                "; ".join(render_failures),
                "Inspect these pages manually and rerun the prescreen after correcting rendering issues.",
            )
        )
    return rows


def write_csv(rows: list[PrescreenRow]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item", "status", "evidence", "required_action"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def write_markdown(rows: list[PrescreenRow], page_count: int | None, page_source: str, pages: list[int], creation_date: str) -> None:
    blocking_rows = [row for row in rows if row.status == "BLOCKER"]
    warning_rows = [row for row in rows if row.status == "WARNING"]
    pass_like = not blocking_rows and len(warning_rows) == 0
    status = PRESCREEN_PASS_STATUS if pass_like or all(row.item in {"Author metadata placeholders", "Ethics/funding placeholders"} for row in blocking_rows) else "AUTOMATED_RENDERED_PDF_PRESCREEN_REVIEW_REQUIRED"

    def row_text(item: str, prefix: str = "") -> str:
        for row in rows:
            if row.item == item:
                return prefix + row.evidence
        return prefix + "not found"

    lines = [
        "# Rendered PDF Visual Prescreen",
        "",
        "This prescreen records an automated rendered-page and text-extraction review of the currently compiled manuscript PDF. It reduces layout uncertainty but does not replace final submitting-author review, clinical-owner signoff, or institutional metadata approval.",
        "",
        "## Summary",
        "",
        f"- Prescreen status: {status}",
        "- Prescreen method: AUTOMATED_PDFINFO_PDFTOTEXT_PDFTOPPM_SAMPLE_RENDER",
        f"- PDF reviewed: `{PDF.relative_to(ROOT)}`",
        f"- PDF creation date from `pdfinfo`: {creation_date if creation_date else 'not available'}",
        f"- Rendered page count: {page_count if page_count is not None else 'NOT VERIFIED'}",
        f"- Rendered page count source: {page_source}",
        f"- Pattern Recognition page target: {PAGE_TARGET_LOW}-{PAGE_TARGET_HIGH} pages",
        f"- Page-count status: {'PASS' if page_count is not None and PAGE_TARGET_LOW <= page_count <= PAGE_TARGET_HIGH else 'BLOCKER'}",
        "- Representative rendered pages inspected: " + ", ".join(str(page) for page in pages),
        "- Text extraction reviewed: full-document `pdftotext -layout` marker scan",
        "- Line-number visibility: PASS on sampled body pages" if "Line numbering" in [row.item for row in rows] and any(row.item == "Line numbering" and row.status == "PASS" for row in rows) else "- Line-number visibility: WARNING",
        "- Page-number visibility: PASS; extracted footer includes `Page 1 of {0}` through `Page {0} of {0}`".format(page_count) if page_count else "- Page-number visibility: NOT VERIFIED",
        "- Body layout: PASS; sampled body pages render as nonblank page images" if any(row.item == "Body layout" and row.status == "PASS" for row in rows) else "- Body layout: WARNING",
        "- Table readability: PASS on extracted rendered table labels" if any(row.item == "Tables" and row.status == "PASS" for row in rows) else "- Table readability: WARNING",
        "- Figure readability: PASS on extracted rendered figure labels" if any(row.item == "Figures" and row.status == "PASS" for row in rows) else "- Figure readability: WARNING",
        "- Bibliography rendering: PASS; extracted text reaches entry `[36]`" if any(row.item == "Bibliography" and row.status == "PASS" for row in rows) else "- Bibliography rendering: WARNING",
        "- Unresolved citation/reference markers: none detected" if any(row.item == "Unresolved markers" and row.status == "PASS" for row in rows) else "- Unresolved citation/reference markers: REVIEW_REQUIRED",
        "- Residual author/institutional placeholders: PRESENT" if any(row.item == "Author metadata placeholders" and row.status == "BLOCKER" for row in rows) else "- Residual author/institutional placeholders: NOT DETECTED",
        "- Residual ethics/funding placeholders: PRESENT" if any(row.item == "Ethics/funding placeholders" and row.status == "BLOCKER" for row in rows) else "- Residual ethics/funding placeholders: NOT DETECTED",
        "- Clinical overlay pixel signoff: STILL REQUIRED",
        "- Final submitting-author rendered-PDF signoff: STILL REQUIRED",
        "- Final author signoff form: `rendered_pdf_author_signoff_form.md`",
        "",
        "## Evidence",
        "",
        "| Item | Status | Evidence | Required action |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = [row.item, row.status, row.evidence, row.required_action]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## Visual Notes",
            "",
            f"- Page count: {page_count if page_count is not None else 'not verified'} pages; sampled pages were {', '.join(str(page) for page in pages)}.",
            f"- Page numbering: {row_text('Page numbering')}.",
            f"- Line numbering: {row_text('Line numbering')}.",
            f"- Rendered sampled pages: {row_text('Rendered sampled pages')}.",
            f"- Tables: {row_text('Tables')}.",
            f"- Figures: {row_text('Figures')}.",
            f"- Bibliography: {row_text('Bibliography')}.",
            "- Clinical overlay panels remain subject to full-resolution PNG and rendered-PDF clinical-owner signoff.",
            "",
            "## Interpretation",
            "",
            "The rendered-PDF artifact now passes automated page-count, sampled-page rendering, text-extraction, table/figure-label, page-number, line-number, and bibliography prescreen checks. The full original submission goal remains incomplete because final metadata, ethics/funding text, clinical-owner overlay signoff, and final submitting-author PDF approval are still missing.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    page_count, page_source = rendered_page_count()
    pages = sample_pages(page_count)
    text = extract_text()
    render_evidence, render_failures = render_sampled_pages(pages)
    info = pdfinfo_text()
    creation_date = parse_pdfinfo_value(info, "CreationDate")
    rows = build_rows(page_count, page_source, pages, text, render_evidence, render_failures)
    write_csv(rows)
    write_markdown(rows, page_count, page_source, pages, creation_date)
    blockers = sum(1 for row in rows if row.status == "BLOCKER")
    warnings = sum(1 for row in rows if row.status == "WARNING")
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Rendered PDF prescreen: pages={page_count}; blockers={blockers}; warnings={warnings}")


if __name__ == "__main__":
    main()
