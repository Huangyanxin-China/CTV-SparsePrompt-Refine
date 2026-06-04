#!/usr/bin/env python3
"""Create the final PDF compilation and rendered-layout handoff."""

from __future__ import annotations

import csv
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "pdf_compilation_handoff.md"
CSV_OUT = ROOT / "reports" / "vsi_pdf_compilation_handoff_20260531.csv"
KNOWN_TOOL_DIRS = [Path("/tmp/vsi_tectonic_env/bin")]
PAGE_TARGET_LOW = 20
PAGE_TARGET_HIGH = 35


@dataclass(frozen=True)
class Row:
    item: str
    status: str
    evidence: str
    required_action: str


def read(rel: str) -> str:
    path = PKG / rel
    return path.read_text() if path.exists() else ""


def tool_path(tool: str) -> str:
    found = shutil.which(tool)
    if found:
        return found
    for directory in KNOWN_TOOL_DIRS:
        candidate = directory / tool
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def accepted_backend() -> tuple[str, str]:
    latexmk = tool_path("latexmk")
    if latexmk:
        return "latexmk", latexmk
    tectonic = tool_path("tectonic")
    if tectonic:
        return "tectonic", tectonic
    return "none", ""


def tool_status(tool: str) -> Row:
    path = tool_path(tool)
    fallback_available = accepted_backend()[0] == "tectonic"
    return Row(
        f"TeX tool: {tool}",
        "PASS" if path else "WARNING" if fallback_available else "BLOCKER",
        path or "not found on PATH",
        "Tectonic fallback is available for PDF compilation." if not path and fallback_available else "Install or use a TeX environment that provides this tool." if not path else "No action.",
    )


def pdf_page_count() -> tuple[int | None, str]:
    main_pdf = PKG / "main.pdf"
    if not main_pdf.exists():
        return None, "not available"
    pdfinfo = tool_path("pdfinfo")
    if pdfinfo:
        import subprocess

        result = subprocess.run(
            [pdfinfo, str(main_pdf)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0:
            match = re.search(r"^Pages:\s*(\d+)\s*$", result.stdout, re.M)
            if match:
                return int(match.group(1)), "pdfinfo"
    try:
        data = main_pdf.read_bytes()
    except OSError:
        return None, "not available"
    count = len(re.findall(rb"/Type\s*/Page\b", data))
    return (count, "raw PDF /Type /Page count") if count else (None, "not available")


def contains(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def build_rows() -> list[Row]:
    tex_audit = read("tex_compile_readiness_audit.md")
    layout_audit = read("source_layout_audit.md")
    main_pdf = PKG / "main.pdf"
    main_log = PKG / "main.log"
    backend, backend_path = accepted_backend()
    page_count, page_source = pdf_page_count()

    rows: list[Row] = []
    for tool in ["latexmk", "pdflatex", "bibtex", "kpsewhich"]:
        rows.append(tool_status(tool))
    rows.append(
        Row(
            "Accepted PDF compile backend",
            "PASS" if backend != "none" else "BLOCKER",
            f"{backend}: {backend_path}" if backend_path else "none",
            "Provide either latexmk/pdflatex or Tectonic before final PDF compilation.",
        )
    )
    rows.append(
        Row(
            "Alternative TeX tool: tectonic",
            "PASS" if tool_path("tectonic") else "WARNING",
            tool_path("tectonic") or "not found on PATH",
            "Use as the accepted fallback backend when latexmk/pdflatex are unavailable.",
        )
    )

    rows.extend(
        [
            Row(
                "Source-level TeX checks",
                "PASS" if contains(tex_audit, "Source readiness status: SOURCE_CHECKS_PASS") and contains(tex_audit, "Source-level failure count: 0") else "BLOCKER",
                "tex_compile_readiness_audit.md",
                "Resolve source-level LaTeX failures before attempting final PDF compilation.",
            ),
            Row(
                "Source-level page estimate",
                "PASS" if contains(layout_audit, "Source-level status: ESTIMATE_IN_RANGE") else "WARNING",
                "source_layout_audit.md",
                "Use only as a risk estimate; inspect rendered PDF page count after compilation.",
            ),
            Row(
                "Rendered PDF file",
                "PASS" if main_pdf.exists() else "BLOCKER",
                str(main_pdf) if main_pdf.exists() else "main.pdf not present",
                "Run `make -C manuscript_vsi_biomedical_data pdf` in a TeX-enabled environment.",
            ),
            Row(
                "LaTeX log file",
                "PASS" if main_log.exists() else "BLOCKER",
                str(main_log) if main_log.exists() else "main.log not present",
                "Inspect the log after compiling for undefined references, missing citations, missing files, and severe layout warnings.",
            ),
            Row(
                "Rendered page-count inspection",
                "PASS" if page_count is not None and PAGE_TARGET_LOW <= page_count <= PAGE_TARGET_HIGH else "BLOCKER",
                f"{page_count} pages by {page_source}" if page_count is not None else "not verified",
                "Open main.pdf and confirm the rendered page count matches the automated count and remains within the Pattern Recognition regular-article range.",
            ),
            Row(
                "Rendered line/page numbering inspection",
                "MANUAL_REQUIRED",
                "source requests line numbers and numbered pages",
                "Confirm line numbers and page numbers are visible throughout the compiled manuscript.",
            ),
            Row(
                "Rendered table and figure inspection",
                "MANUAL_REQUIRED",
                "10 tables and 7 manuscript figures are source-verified",
                "Confirm tables, figures, captions, and labels are readable, non-overlapping, and appear with the intended content.",
            ),
            Row(
                "Rendered bibliography inspection",
                "MANUAL_REQUIRED",
                "36 cited BibTeX entries are source-verified",
                "Confirm the bibliography renders, citations are numbered, and no citation placeholders remain.",
            ),
        ]
    )
    return rows


def write_csv(rows: list[Row]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item", "status", "evidence", "required_action"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "item": row.item,
                    "status": row.status,
                    "evidence": row.evidence,
                    "required_action": row.required_action,
                }
            )


def write_markdown(rows: list[Row]) -> None:
    blockers = sum(1 for row in rows if row.status == "BLOCKER")
    manual = sum(1 for row in rows if row.status == "MANUAL_REQUIRED")
    status = "BLOCKED_NO_RENDERED_PDF" if blockers else "READY_FOR_RENDERED_PDF_INSPECTION"

    lines = [
        "# PDF Compilation Handoff",
        "",
        "This handoff records the final PDF compilation and rendered-layout inspection gates. Source-level checks are useful risk controls but do not prove rendered PDF compliance.",
        "",
        "## Summary",
        "",
        f"- PDF handoff status: {status}",
        f"- Blocking PDF compile items: {blockers}",
        f"- Manual rendered-PDF inspection items: {manual}",
        f"- Accepted PDF compile backend: {accepted_backend()[0]}",
        "- Compile command in a TeX-enabled environment: `make -C manuscript_vsi_biomedical_data pdf`",
        "- Tectonic fallback compile/audit command: `make -C manuscript_vsi_biomedical_data pdf-render-compile`",
        "- Clean command after inspection if needed: `make -C manuscript_vsi_biomedical_data clean`",
        "- Expected PDF output: `manuscript_vsi_biomedical_data/main.pdf`",
        "- Expected log output: `manuscript_vsi_biomedical_data/main.log`",
        "- Render audit command without compiling: `make -C manuscript_vsi_biomedical_data pdf-render-audit`",
        "- Compile-and-render-audit command: `make -C manuscript_vsi_biomedical_data pdf-render-compile`",
        "- Render audit output: `manuscript_vsi_biomedical_data/pdf_render_audit.md`",
        "- Final author signoff form: `rendered_pdf_author_signoff_form.md`",
        "",
        "## Gate Table",
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
            "## Required Rendered-PDF Inspection",
            "",
            "1. Run `make -C manuscript_vsi_biomedical_data pdf` in an environment with `latexmk`, `pdflatex`, `bibtex`, and the included CAS files, or run `make -C manuscript_vsi_biomedical_data pdf-render-compile` with the accepted Tectonic fallback.",
            "2. Confirm `main.pdf` and `main.log` are produced.",
            "3. Run `make -C manuscript_vsi_biomedical_data pdf-render-audit`, or use `make -C manuscript_vsi_biomedical_data pdf-render-compile` to compile and audit in one step.",
            "4. Inspect `main.log` for undefined references, missing citations, missing files, and fatal errors.",
            "5. Open `main.pdf` and confirm single-column layout, double spacing, line numbers, numbered pages, and the rendered page count.",
            "6. Inspect all figures, tables, captions, and bibliography entries for readability and non-overlap.",
            "7. Record final submitting-author decisions in `rendered_pdf_author_signoff_form.md`.",
            "8. After PDF inspection and metadata finalization, rerun `make -C manuscript_vsi_biomedical_data release`.",
            "",
            "## Non-Substitutable Evidence",
            "",
            "- `tex_compile_readiness_audit.md` cannot prove final page count or rendered layout.",
            "- `source_layout_audit.md` is an estimate, not final PDF evidence.",
            "- Archive integrity cannot prove that `main.pdf` was compiled or inspected.",
            "- `pdf_render_audit.md` can prove tool/PDF/log/page-count status, but it cannot replace human visual inspection of the rendered PDF.",
            "- `rendered_pdf_author_signoff_form.md` is required to close the final rendered-PDF inspection blocker.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    blockers = sum(1 for row in rows if row.status == "BLOCKER")
    manual = sum(1 for row in rows if row.status == "MANUAL_REQUIRED")
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"PDF handoff: blockers={blockers}; manual={manual}")


if __name__ == "__main__":
    main()
