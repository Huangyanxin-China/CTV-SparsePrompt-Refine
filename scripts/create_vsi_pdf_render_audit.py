#!/usr/bin/env python3
"""Create or update the rendered-PDF audit for the VSI manuscript package."""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "pdf_render_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_pdf_render_audit_20260531.csv"
MAIN_TEX = PKG / "main.tex"
MAIN_PDF = PKG / "main.pdf"
MAIN_LOG = PKG / "main.log"
PAGE_TARGET_LOW = 20
PAGE_TARGET_HIGH = 35
LATEXMK_REQUIRED_TOOLS = ["latexmk", "pdflatex", "bibtex", "kpsewhich"]
ALTERNATIVE_TEX_TOOLS = ["tectonic"]
OPTIONAL_TOOLS = ["pdfinfo"]
KNOWN_TOOL_DIRS = [Path("/tmp/vsi_tectonic_env/bin")]
DEFAULT_TECTONIC_BUNDLE = "https://relay.fullyjustified.net/default_bundle_v32.tar"


@dataclass(frozen=True)
class AuditRow:
    item: str
    status: str
    evidence: str
    required_action: str


@dataclass(frozen=True)
class CompileResult:
    attempted: bool
    return_code: str
    stdout_tail: str
    stderr_tail: str
    backend: str
    command: str


def tail_text(text: str, max_lines: int = 80) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


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


def run_compile(timeout: int) -> CompileResult:
    backend, executable = accepted_backend()
    if backend == "none":
        return CompileResult(False, "not run: no accepted TeX backend available", "", "", "none", "")
    if backend == "latexmk":
        command = [executable, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        env = None
    else:
        bundle = os.environ.get("TECTONIC_BUNDLE", DEFAULT_TECTONIC_BUNDLE)
        command = [executable, "--bundle", bundle, "--keep-logs", "--keep-intermediates", "-p", "main.tex"]
        env = os.environ.copy()
        env.setdefault("XDG_CACHE_HOME", "/tmp/tectonic-cache")
    result = subprocess.run(
        command,
        cwd=PKG,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=env,
    )
    return CompileResult(
        True,
        str(result.returncode),
        tail_text(result.stdout),
        tail_text(result.stderr),
        backend,
        " ".join(command),
    )


def pdf_page_count_with_pdfinfo() -> int | None:
    pdfinfo = tool_path("pdfinfo")
    if not pdfinfo or not MAIN_PDF.exists():
        return None
    result = subprocess.run(
        [pdfinfo, str(MAIN_PDF)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    match = re.search(r"^Pages:\s*(\d+)\s*$", result.stdout, re.M)
    return int(match.group(1)) if match else None


def pdf_page_count_fallback() -> int | None:
    if not MAIN_PDF.exists():
        return None
    try:
        data = MAIN_PDF.read_bytes()
    except OSError:
        return None
    count = len(re.findall(rb"/Type\s*/Page\b", data))
    return count or None


def rendered_page_count() -> tuple[int | None, str]:
    page_count = pdf_page_count_with_pdfinfo()
    if page_count is not None:
        return page_count, "pdfinfo"
    page_count = pdf_page_count_fallback()
    if page_count is not None:
        return page_count, "raw PDF /Type /Page count"
    return None, "not available"


def scan_log() -> tuple[list[str], list[str]]:
    if not MAIN_LOG.exists():
        return [], []
    text = MAIN_LOG.read_text(errors="replace")
    severe_patterns = [
        r"! LaTeX Error:",
        r"Emergency stop",
        r"Fatal error",
        r"Undefined control sequence",
        r"File `[^']+' not found",
    ]
    warning_patterns = [
        r"LaTeX Warning: Citation .* undefined",
        r"LaTeX Warning: Reference .* undefined",
        r"There were undefined references",
        r"Rerun to get cross-references right",
        r"Overfull \\hbox",
        r"Underfull \\hbox",
    ]
    severe = []
    warnings = []
    for line in text.splitlines():
        if any(re.search(pattern, line) for pattern in severe_patterns):
            severe.append(" ".join(line.split()))
        if any(re.search(pattern, line) for pattern in warning_patterns):
            warnings.append(" ".join(line.split()))
    return severe, warnings


def compile_result_to_rows(result: CompileResult) -> list[AuditRow]:
    reusing_existing_pdf = not result.attempted and MAIN_PDF.exists() and MAIN_LOG.exists()
    rows = [
        AuditRow(
            "Accepted PDF compile backend",
            "PASS" if accepted_backend()[0] != "none" else "BLOCKER",
            accepted_backend()[0],
            "Install latexmk/pdflatex or Tectonic before compiling the manuscript PDF.",
        ),
        AuditRow(
            "Compile attempted",
            "PASS" if result.attempted or reusing_existing_pdf else "BLOCKER",
            "YES" if result.attempted else "NO; reusing existing main.pdf/main.log" if reusing_existing_pdf else "NO",
            "Run `python scripts/create_vsi_pdf_render_audit.py --compile` after any source change.",
        ),
        AuditRow(
            "Compile return code",
            "PASS" if result.return_code == "0" else "WARNING" if reusing_existing_pdf else "BLOCKER",
            result.return_code,
            "If nonzero, inspect main.log and fix LaTeX or bibliography errors before submission.",
        ),
        AuditRow(
            "Compile backend used",
            "PASS" if result.backend != "none" else "WARNING",
            result.backend,
            "Retain the backend name with the audit record.",
        ),
    ]
    if result.command:
        rows.append(
            AuditRow(
                "Compile command captured",
                "PASS",
                result.command,
                "Retain the command with the audit record.",
            )
        )
    if result.stdout_tail:
        rows.append(
            AuditRow(
                "Compile stdout tail captured",
                "PASS",
                result.stdout_tail.replace("\n", " / "),
                "Retain stdout tail for debugging if compilation fails.",
            )
        )
    if result.stderr_tail:
        rows.append(
            AuditRow(
                "Compile stderr tail captured",
                "WARNING",
                result.stderr_tail.replace("\n", " / "),
                "Inspect stderr for external-tool failures.",
            )
        )
    return rows


def build_rows(result: CompileResult) -> list[AuditRow]:
    rows: list[AuditRow] = []
    backend, backend_path = accepted_backend()
    alternative_available = backend == "tectonic"
    for tool in LATEXMK_REQUIRED_TOOLS:
        found = tool_path(tool)
        rows.append(
            AuditRow(
                f"Required TeX tool: {tool}",
                "PASS" if found else "WARNING" if alternative_available else "BLOCKER",
                found or "not found on PATH",
                "Tectonic fallback is available for this audit." if not found and alternative_available else "Install or use a TeX environment that provides this tool." if not found else "No action.",
            )
        )
    for tool in ALTERNATIVE_TEX_TOOLS:
        found = tool_path(tool)
        rows.append(
            AuditRow(
                f"Alternative TeX tool: {tool}",
                "PASS" if found else "WARNING",
                found or "not found on PATH",
                "Use this as the accepted fallback backend when latexmk/pdflatex are unavailable." if found else "Install only if latexmk/pdflatex are unavailable.",
            )
        )
    rows.append(
        AuditRow(
            "Accepted TeX backend path",
            "PASS" if backend_path else "BLOCKER",
            backend_path or "none",
            "Provide either latexmk/pdflatex or Tectonic before final PDF compilation.",
        )
    )
    for tool in OPTIONAL_TOOLS:
        found = tool_path(tool)
        rows.append(
            AuditRow(
                f"Optional PDF audit tool: {tool}",
                "PASS" if found else "WARNING",
                found or "not found on PATH",
                "Install for more reliable PDF page-count extraction, or use manual PDF inspection.",
            )
        )

    rows.extend(compile_result_to_rows(result))

    page_count, page_source = rendered_page_count()
    severe_log, warning_log = scan_log()
    rows.extend(
        [
            AuditRow(
                "Main TeX source",
                "PASS" if MAIN_TEX.exists() else "BLOCKER",
                str(MAIN_TEX) if MAIN_TEX.exists() else "main.tex not present",
                "Restore the manuscript source before attempting PDF compilation.",
            ),
            AuditRow(
                "Rendered PDF file",
                "PASS" if MAIN_PDF.exists() else "BLOCKER",
                str(MAIN_PDF) if MAIN_PDF.exists() else "main.pdf not present",
                "Run the compile command in a TeX-enabled environment.",
            ),
            AuditRow(
                "LaTeX log file",
                "PASS" if MAIN_LOG.exists() else "BLOCKER",
                str(MAIN_LOG) if MAIN_LOG.exists() else "main.log not present",
                "Compile with the accepted backend, then inspect the log for unresolved errors and warnings.",
            ),
            AuditRow(
                "Rendered page count",
                "PASS" if page_count is not None and PAGE_TARGET_LOW <= page_count <= PAGE_TARGET_HIGH else "BLOCKER",
                f"{page_count} pages by {page_source}" if page_count is not None else "not verified",
                f"Confirm final PDF page count is within {PAGE_TARGET_LOW}-{PAGE_TARGET_HIGH} pages.",
            ),
            AuditRow(
                "Severe LaTeX log issues",
                "PASS" if MAIN_LOG.exists() and not severe_log else "BLOCKER",
                f"{len(severe_log)} issue(s)" if MAIN_LOG.exists() else "main.log not present",
                "Resolve all fatal LaTeX errors, undefined control sequences, and missing-file errors.",
            ),
            AuditRow(
                "Nonfatal LaTeX log warnings",
                "PASS" if MAIN_LOG.exists() and not warning_log else "WARNING",
                f"{len(warning_log)} warning(s)" if MAIN_LOG.exists() else "main.log not present",
                "Review undefined references, undefined citations, rerun requests, and overfull boxes.",
            ),
            AuditRow(
                "Manual line/page-number inspection",
                "MANUAL_REQUIRED",
                "source requests line numbers and numbered pages",
                "Open main.pdf and confirm line numbers and page numbers are visible on the rendered manuscript.",
            ),
            AuditRow(
                "Manual figure/table inspection",
                "MANUAL_REQUIRED",
                "figures and tables are source-verified but not visually inspected in rendered PDF",
                "Confirm all figures, tables, captions, labels, and legends are readable and non-overlapping.",
            ),
            AuditRow(
                "Manual bibliography inspection",
                "MANUAL_REQUIRED",
                "36 cited BibTeX entries are source-verified",
                "Confirm citations render numerically and the bibliography has no placeholders.",
            ),
            AuditRow(
                "Manual clinical overlay inspection in PDF",
                "MANUAL_REQUIRED",
                "clinical_overlay_visual_review_packet.md remains the pixel-review queue",
                "Inspect clinical overlay figures again in the rendered PDF after compilation.",
            ),
        ]
    )
    if severe_log:
        rows.append(
            AuditRow(
                "Severe LaTeX log issue examples",
                "BLOCKER",
                " / ".join(severe_log[:5]),
                "Use the log examples to locate and repair compile failures.",
            )
        )
    if warning_log:
        rows.append(
            AuditRow(
                "Nonfatal LaTeX log warning examples",
                "WARNING",
                " / ".join(warning_log[:5]),
                "Review warnings before upload; fix any undefined references or citations.",
            )
        )
    return rows


def status_for(rows: list[AuditRow], result: CompileResult) -> str:
    ignored_when_reusing_existing_pdf = {"Compile attempted", "Compile return code"}
    severe_blockers = [
        row
        for row in rows
        if row.status == "BLOCKER"
        and not (not result.attempted and row.item in ignored_when_reusing_existing_pdf and MAIN_PDF.exists() and MAIN_LOG.exists())
    ]
    if accepted_backend()[0] == "none":
        return "BLOCKED_NO_TEX_TOOLCHAIN"
    if result.attempted and result.return_code != "0":
        return "COMPILE_FAILED"
    if not MAIN_PDF.exists() or not MAIN_LOG.exists():
        return "BLOCKED_NO_RENDERED_PDF"
    if severe_blockers:
        return "RENDERED_PDF_REPAIR_REQUIRED"
    return "READY_FOR_MANUAL_RENDERED_PDF_REVIEW"


def write_csv(rows: list[AuditRow]) -> None:
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


def write_markdown(rows: list[AuditRow], result: CompileResult, audit_status: str) -> None:
    blockers = sum(1 for row in rows if row.status == "BLOCKER")
    warnings = sum(1 for row in rows if row.status == "WARNING")
    manual = sum(1 for row in rows if row.status == "MANUAL_REQUIRED")
    missing_tex = [tool for tool in LATEXMK_REQUIRED_TOOLS if not tool_path(tool)]
    backend, backend_path = accepted_backend()
    page_count, page_source = rendered_page_count()
    severe_log, warning_log = scan_log()
    lines = [
        "# PDF Render Audit",
        "",
        "This audit is the executable companion to `pdf_compilation_handoff.md`. It can be run without TeX to preserve the current blocker state, or with `--compile` in a TeX-enabled environment to compile and inspect the rendered PDF artifacts.",
        "",
        "## Summary",
        "",
        f"- PDF render audit status: {audit_status}",
        f"- Compile attempted: {'YES' if result.attempted else 'NO'}",
        f"- Compile return code: {result.return_code}",
        f"- Accepted TeX backend: {backend}",
        f"- Accepted TeX backend path: {backend_path if backend_path else 'none'}",
        f"- Legacy latexmk toolchain missing: {', '.join(missing_tex) if missing_tex else 'none'}",
        f"- Main PDF present: {'YES' if MAIN_PDF.exists() else 'NO'}",
        f"- Main log present: {'YES' if MAIN_LOG.exists() else 'NO'}",
        f"- Rendered page count: {page_count if page_count is not None else 'NOT VERIFIED'}",
        f"- Rendered page count source: {page_source}",
        f"- Page range target: {PAGE_TARGET_LOW}-{PAGE_TARGET_HIGH} pages",
        f"- Severe LaTeX log issues: {len(severe_log) if MAIN_LOG.exists() else 'NOT VERIFIED'}",
        f"- Nonfatal LaTeX log warnings: {len(warning_log) if MAIN_LOG.exists() else 'NOT VERIFIED'}",
        f"- Blocking audit rows: {blockers}",
        f"- Warning audit rows: {warnings}",
        f"- Manual rendered review rows: {manual}",
        "- Manual rendered review status: REQUIRED_AFTER_COMPILE",
        "- Audit-only command: `python scripts/create_vsi_pdf_render_audit.py`",
        "- Compile-and-audit command: `python scripts/create_vsi_pdf_render_audit.py --compile`",
        f"- Tectonic fallback bundle: `{os.environ.get('TECTONIC_BUNDLE', DEFAULT_TECTONIC_BUNDLE)}`",
        "- Makefile audit target: `make -C manuscript_vsi_biomedical_data pdf-render-audit`",
        "- Makefile compile target: `make -C manuscript_vsi_biomedical_data pdf-render-compile`",
        "- Final author signoff form: `rendered_pdf_author_signoff_form.md`",
        "",
        "## Audit Table",
        "",
        "| Item | Status | Evidence | Required action |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = [row.item, row.status, row.evidence, row.required_action]
        lines.append("| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## Required Manual Checks After Successful Compile",
            "",
            "1. Confirm the rendered PDF is single-column, double-spaced, line-numbered, and page-numbered.",
            f"2. Confirm the rendered page count is within {PAGE_TARGET_LOW}-{PAGE_TARGET_HIGH} pages.",
            "3. Inspect all figures, tables, captions, labels, equations, and bibliography entries for readability and non-overlap.",
            "4. Recheck clinical overlay figures in the rendered PDF using `clinical_overlay_visual_review_packet.md`.",
            "5. Record final submitting-author rendered-PDF decisions in `rendered_pdf_author_signoff_form.md`.",
            "6. Rerun `make -C manuscript_vsi_biomedical_data release` after any source, bibliography, figure, or metadata changes.",
            "",
            "## Completion Rule",
            "",
            "This audit can clear the environment and artifact portion of the PDF blocker only when it reports `READY_FOR_MANUAL_RENDERED_PDF_REVIEW`, the rendered page count is in range, and the submitting author records manual rendered-PDF inspection in `rendered_pdf_author_signoff_form.md`.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a rendered-PDF audit for the VSI manuscript package.")
    parser.add_argument("--compile", action="store_true", help="Run the accepted TeX backend before auditing PDF/log artifacts.")
    parser.add_argument("--timeout", type=int, default=600, help="Compilation timeout in seconds when --compile is used.")
    args = parser.parse_args()

    result = run_compile(args.timeout) if args.compile else CompileResult(False, "not run", "", "", "none", "")
    rows = build_rows(result)
    audit_status = status_for(rows, result)
    write_csv(rows)
    write_markdown(rows, result, audit_status)
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"PDF render audit status: {audit_status}; compile_attempted={result.attempted}; rows={len(rows)}")


if __name__ == "__main__":
    main()
