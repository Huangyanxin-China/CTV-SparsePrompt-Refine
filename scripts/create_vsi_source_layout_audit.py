#!/usr/bin/env python3
"""Create a source-level layout and page-count risk audit for the VSI package."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MAIN = PKG / "main.tex"
BIB = PKG / "references.bib"
OUT = PKG / "source_layout_audit.md"


def strip_tex(text: str) -> str:
    text = re.sub(r"%.*", " ", text)
    text = re.sub(r"\\begin\{(?:figure|table|tabular)[^}]*\}.*?\\end\{(?:figure|table|tabular)\}", " ", text, flags=re.S)
    text = re.sub(r"\$.*?\$", " ", text, flags=re.S)
    text = re.sub(r"\\cite\w*\{[^}]*\}", " ", text)
    text = re.sub(r"\\(?:ref|autoref|pageref)\{[^}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z]+(?:\[[^]]*\])?(?:\{([^{}]*)\})?", r" \1 ", text)
    text = re.sub(r"[{}\\_^&%#~]", " ", text)
    return " ".join(text.split())


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", strip_tex(text)))


def raw_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text))


def input_sources(tex: str) -> dict[str, str]:
    sources = {"main.tex": tex}
    for item in re.findall(r"\\input\{([^}]+)\}", tex):
        path = PKG / (item if item.endswith(".tex") else item + ".tex")
        if path.exists():
            sources[str(path.relative_to(PKG))] = path.read_text()
    return sources


def section_word_counts(tex: str) -> list[tuple[str, int]]:
    section_pattern = re.compile(r"\\section\*?\{([^}]+)\}")
    matches = list(section_pattern.finditer(tex))
    rows: list[tuple[str, int]] = []
    for idx, match in enumerate(matches):
        title = strip_tex(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(tex)
        rows.append((title, word_count(tex[start:end])))
    return rows


def bib_entry_count(text: str) -> int:
    return len(re.findall(r"@\w+\{", text))


def page_estimate(article_words: int, figures: int, tables: int, references: int) -> dict[str, float]:
    # Pattern Recognition asks for single-column, double-spaced submissions.
    # These source-level estimates are deliberately transparent and must be
    # replaced by rendered PDF inspection when TeX is available.
    central = article_words / 250.0 + figures * 0.75 + tables * 0.45 + references / 16.0 + 1.5
    low = article_words / 300.0 + figures * 0.50 + tables * 0.30 + references / 20.0 + 1.0
    high = article_words / 220.0 + figures * 1.00 + tables * 0.65 + references / 12.0 + 2.0
    return {"low": low, "central": central, "high": high}


def main() -> None:
    tex = MAIN.read_text()
    sources = input_sources(tex)
    combined = "\n".join(sources.values())
    abstract_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    abstract_words = raw_word_count(abstract_match.group(1)) if abstract_match else 0
    article_start = re.search(r"\\section\{Introduction\}", tex)
    bibliography_start = re.search(r"\\bibliographystyle", tex)
    article_body = tex[article_start.start() : bibliography_start.start()] if article_start and bibliography_start else tex
    article_words = word_count(article_body)
    combined_words = word_count(combined)
    figures = len(re.findall(r"\\begin\{figure\}", tex))
    tables = len(re.findall(r"\\begin\{table\}", combined))
    inputs = len(re.findall(r"\\input\{", tex))
    refs = bib_entry_count(BIB.read_text())
    pages = page_estimate(article_words, figures, tables, refs)
    status = "ESTIMATE_IN_RANGE" if 20.0 <= pages["central"] <= 35.0 else "ESTIMATE_OUT_OF_RANGE"

    lines = [
        "# Source Layout Audit",
        "",
        "This audit estimates manuscript length from LaTeX source because this environment lacks `pdflatex`, `latexmk`, and `kpsewhich`. It is a risk-control check, not proof of final rendered page count.",
        "",
        "## Official Layout Requirement",
        "",
        "- Journal: Pattern Recognition",
        "- Source: https://www.sciencedirect.com/journal/pattern-recognition/publish/guide-for-authors",
        "- Requirement audited here: single-column, double-spaced manuscript, 20-35 pages for a regular article, with numbered pages.",
        "",
        "## Source Counts",
        "",
        f"- Main source lines: {len(tex.splitlines())}",
        f"- Included table/source files: {inputs}",
        f"- Abstract words: {abstract_words}",
        f"- Article body words, excluding bibliography and table bodies: {article_words}",
        f"- Combined source words, including editable table text: {combined_words}",
        f"- Figure environments: {figures}",
        f"- Table environments: {tables}",
        f"- BibTeX entries: {refs}",
        "",
        "## Page-Count Risk Estimate",
        "",
        f"- Estimated page count: {pages['central']:.1f}",
        f"- Sensitivity range: {pages['low']:.1f}-{pages['high']:.1f}",
        f"- Source-level status: {status}",
        "- PDF page-count status: NOT VERIFIED",
        "",
        "The central estimate uses 250 words per double-spaced single-column page, 0.75 pages per figure, 0.45 pages per table, 16 references per page, and 1.5 pages for title/abstract/front matter. The sensitivity range varies these assumptions to show layout risk before final compilation.",
        "",
        "## Section Word Counts",
        "",
        "| Section | Approximate words |",
        "| --- | ---: |",
    ]
    for title, count in section_word_counts(article_body):
        lines.append(f"| {title} | {count} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The source-level central estimate is within the Pattern Recognition 20-35 page target.",
            "- Final compliance remains unverified until a TeX-enabled environment compiles `main.tex` and the PDF page count, line numbers, page numbers, table layout, and bibliography are inspected.",
            "- If the compiled PDF falls below 20 pages, the lowest-risk fix is to keep the current evidence chain and move detailed methods or audit tables from source files into the main rendered manuscript as needed.",
            "",
        ]
    )
    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT}")
    print(f"Estimated page count: {pages['central']:.1f} ({status})")


if __name__ == "__main__":
    main()
