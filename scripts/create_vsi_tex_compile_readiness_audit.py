#!/usr/bin/env python3
"""Create a TeX compile-readiness audit without requiring a TeX installation."""

from __future__ import annotations

import csv
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MAIN = PKG / "main.tex"
BIB = PKG / "references.bib"
OUT_MD = PKG / "tex_compile_readiness_audit.md"
OUT_CSV = ROOT / "reports" / "vsi_tex_compile_readiness_audit_20260531.csv"
KNOWN_TOOL_DIRS = [Path("/tmp/vsi_tectonic_env/bin")]


@dataclass(frozen=True)
class AuditRow:
    check: str
    status: str
    detail: str


def strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        out = []
        escaped = False
        for char in line:
            if char == "\\" and not escaped:
                escaped = True
                out.append(char)
                continue
            if char == "%" and not escaped:
                break
            out.append(char)
            escaped = False
        lines.append("".join(out))
    return "\n".join(lines)


def unescaped_count(text: str, char: str) -> int:
    count = 0
    escaped = False
    for current in text:
        if current == "\\" and not escaped:
            escaped = True
            continue
        if current == char and not escaped:
            count += 1
        escaped = False
    return count


def add(rows: list[AuditRow], check: str, ok: bool, detail: object) -> None:
    rows.append(AuditRow(check, "PASS" if ok else "FAIL", str(detail)))


def warn(rows: list[AuditRow], check: str, detail: object) -> None:
    rows.append(AuditRow(check, "WARNING", str(detail)))


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


def bib_keys(text: str) -> set[str]:
    return set(re.findall(r"@\w+\{([^,]+),", text))


def citation_keys(text: str) -> set[str]:
    used: set[str] = set()
    for body in re.findall(r"\\cite\w*\{([^}]+)\}", text):
        used.update(key.strip() for key in body.split(",") if key.strip())
    return used


def tex_labels(text: str) -> list[str]:
    return re.findall(r"\\label\{([^}]+)\}", text)


def tex_refs(text: str) -> list[str]:
    refs = []
    for body in re.findall(r"\\(?:ref|autoref|pageref)\{([^}]+)\}", text):
        refs.extend(item.strip() for item in body.split(",") if item.strip())
    return refs


def input_paths(main_text: str) -> list[Path]:
    paths = []
    for item in re.findall(r"\\input\{([^}]+)\}", main_text):
        rel = item if item.endswith(".tex") else item + ".tex"
        paths.append(PKG / rel)
    return paths


def graphics_paths(main_text: str) -> list[Path]:
    return [PKG / item for item in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", main_text)]


def source_map() -> dict[str, str]:
    main_text = MAIN.read_text()
    sources = {"main.tex": main_text}
    for path in input_paths(main_text):
        if path.exists():
            sources[str(path.relative_to(PKG))] = path.read_text()
    return sources


def environment_balance(text: str) -> tuple[bool, str]:
    begins = re.findall(r"\\begin\{([^}]+)\}", text)
    ends = re.findall(r"\\end\{([^}]+)\}", text)
    problems = []
    for env in sorted(set(begins + ends)):
        if begins.count(env) != ends.count(env):
            problems.append(f"{env}: begin={begins.count(env)}, end={ends.count(env)}")
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(begins)} environments"


def brace_balance(text: str) -> tuple[bool, str]:
    clean = strip_comments(text)
    opens = unescaped_count(clean, "{")
    closes = unescaped_count(clean, "}")
    return opens == closes, f"{{={opens}, }}={closes}"


def math_balance(text: str) -> tuple[bool, str]:
    clean = strip_comments(text)
    dollars = unescaped_count(clean, "$")
    return dollars % 2 == 0, f"unescaped dollar delimiters={dollars}"


def ascii_check(text: str) -> tuple[bool, str]:
    hits = sorted({char for char in text if ord(char) > 127})
    if hits:
        return False, "non-ASCII characters: " + ", ".join(repr(char) for char in hits[:8])
    return True, "ASCII only"


def unescaped_percent_lines(text: str) -> list[int]:
    hits = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("%"):
            continue
        escaped = False
        for char in line:
            if char == "\\" and not escaped:
                escaped = True
                continue
            if char == "%" and not escaped:
                hits.append(line_no)
                break
            escaped = False
    return hits


def markdown_code_tick_lines(text: str) -> list[int]:
    return [line_no for line_no, line in enumerate(text.splitlines(), 1) if "`" in line]


def table_file_checks(rows: list[AuditRow]) -> None:
    table_paths = sorted((PKG / "tables").glob("*.tex"))
    add(rows, "table source files present", len(table_paths) >= 10, f"{len(table_paths)} table files")
    for path in table_paths:
        text = path.read_text()
        rel = str(path.relative_to(PKG))
        add(rows, f"{rel}: table environment", r"\begin{table}" in text and r"\end{table}" in text, rel)
        add(rows, f"{rel}: tabular environment", r"\begin{tabular}" in text and r"\end{tabular}" in text, rel)
        add(rows, f"{rel}: caption present", r"\caption" in text, rel)
        add(rows, f"{rel}: label present", r"\label" in text, rel)
        add(rows, f"{rel}: booktabs rules present", all(rule in text for rule in [r"\toprule", r"\midrule", r"\bottomrule"]), rel)
        percent_hits = unescaped_percent_lines(text)
        add(
            rows,
            f"{rel}: no unescaped percent in content rows",
            not percent_hits,
            "none" if not percent_hits else "line(s): " + ", ".join(str(line_no) for line_no in percent_hits[:12]),
        )


def run_audit() -> list[AuditRow]:
    rows: list[AuditRow] = []
    add(rows, "main.tex exists", MAIN.exists(), MAIN)
    add(rows, "references.bib exists", BIB.exists(), BIB)
    for rel in ["cas-sc.cls", "cas-common.sty", "cas-model2-names.bst"]:
        add(rows, f"local CAS support file exists: {rel}", (PKG / rel).exists(), PKG / rel)
    if not MAIN.exists() or not BIB.exists():
        return rows

    main_text = MAIN.read_text()
    sources = source_map()
    combined = "\n".join(sources.values())
    bib_text = BIB.read_text()

    add(
        rows,
        "single-column CAS review class requested",
        r"\documentclass[a4paper,12pt,fleqn,review]{cas-sc}" in main_text,
        "cas-sc 12pt review",
    )
    add(rows, "double spacing command present", r"\doublespacing" in main_text, "setspace")
    add(rows, "line numbers command present", r"\linenumbers" in main_text, "lineno")
    add(rows, "bibliography style present", r"\bibliographystyle{cas-model2-names}" in main_text, "cas-model2-names")
    add(rows, "bibliography command present", r"\bibliography{references}" in main_text, "references")
    add(rows, "maketitle present", r"\maketitle" in main_text, "main.tex")

    inputs = input_paths(main_text)
    add(rows, "all input files exist", all(path.exists() for path in inputs), ", ".join(str(path.relative_to(PKG)) for path in inputs))
    graphics = graphics_paths(main_text)
    add(rows, "all included graphics exist", all(path.exists() for path in graphics), ", ".join(str(path.relative_to(PKG)) for path in graphics))

    for rel, text in sources.items():
        ok, detail = brace_balance(text)
        add(rows, f"{rel}: balanced braces", ok, detail)
        ok, detail = math_balance(text)
        add(rows, f"{rel}: balanced math dollar delimiters", ok, detail)
        ok, detail = environment_balance(text)
        add(rows, f"{rel}: begin/end environments balanced", ok, detail)
        ok, detail = ascii_check(text)
        add(rows, f"{rel}: ASCII source", ok, detail)
        tick_hits = markdown_code_tick_lines(text)
        add(
            rows,
            f"{rel}: no Markdown code ticks",
            not tick_hits,
            "none" if not tick_hits else "line(s): " + ", ".join(str(line_no) for line_no in tick_hits[:12]),
        )

    keys = bib_keys(bib_text)
    used = citation_keys(main_text)
    add(rows, "all cited BibTeX keys exist", not (used - keys), ", ".join(sorted(used - keys)) if used - keys else f"{len(used)} citations")
    add(rows, "all BibTeX entries are cited", not (keys - used), ", ".join(sorted(keys - used)) if keys - used else f"{len(keys)} entries")
    ok, detail = brace_balance(bib_text)
    add(rows, "references.bib balanced braces", ok, detail)
    ok, detail = ascii_check(bib_text)
    add(rows, "references.bib ASCII source", ok, detail)

    labels = tex_labels(combined)
    duplicate_labels = sorted(label for label in set(labels) if labels.count(label) > 1)
    refs = sorted(set(tex_refs(combined)))
    missing_refs = sorted(set(refs) - set(labels))
    add(rows, "no duplicate labels", not duplicate_labels, ", ".join(duplicate_labels) if duplicate_labels else f"{len(labels)} labels")
    add(rows, "all refs resolve", not missing_refs, ", ".join(missing_refs) if missing_refs else f"{len(refs)} refs")

    table_file_checks(rows)

    for tool in ["pdflatex", "latexmk", "kpsewhich"]:
        found = tool_path(tool)
        if found:
            add(rows, f"TeX tool available: {tool}", True, found)
        else:
            warn(rows, f"TeX tool unavailable: {tool}", "Rendered PDF still requires external TeX environment.")
    backend, backend_path = accepted_backend()
    if backend != "none":
        add(rows, f"accepted TeX backend: {backend}", True, backend_path)
    else:
        warn(rows, "accepted TeX backend unavailable", "Provide latexmk/pdflatex or Tectonic before final PDF compilation.")
    return rows


def write_csv(rows: list[AuditRow]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "detail"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"check": row.check, "status": row.status, "detail": row.detail})


def write_markdown(rows: list[AuditRow]) -> None:
    failures = [row for row in rows if row.status == "FAIL"]
    warnings = [row for row in rows if row.status == "WARNING"]
    source_status = "SOURCE_CHECKS_PASS" if not failures else "SOURCE_CHECKS_FAIL"
    lines = [
        "# TeX Compile-Readiness Audit",
        "",
        "This audit checks LaTeX source consistency in an environment without a TeX engine. It is not a substitute for compiling and inspecting the final PDF.",
        "",
        "## Summary",
        "",
        f"- Source readiness status: {source_status}",
        f"- Source-level failure count: {len(failures)}",
        f"- Environment warning count: {len(warnings)}",
        "- Rendered PDF status: NOT VERIFIED",
        f"- Accepted TeX backend for PDF audit: {accepted_backend()[0]}",
        "- Final compile command when TeX is available: `make -C manuscript_vsi_biomedical_data pdf`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        detail = row.detail.replace("|", "\\|")
        lines.append(f"| {row.check} | {row.status} | {detail} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `SOURCE_CHECKS_PASS` means local source checks found no missing inputs, unresolved citations, duplicate labels, unbalanced environments, or obvious table-structure errors.",
            "- `Rendered PDF status: NOT VERIFIED` remains a real submission blocker until a TeX-enabled environment compiles `main.tex` and the PDF page count, line numbers, tables, figures, and bibliography are inspected.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    rows = run_audit()
    write_csv(rows)
    write_markdown(rows)
    failures = [row for row in rows if row.status == "FAIL"]
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(f"Source-level failure count: {len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
