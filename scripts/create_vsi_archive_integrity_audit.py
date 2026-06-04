#!/usr/bin/env python3
"""Audit the dated VSI manuscript tarball after release packaging."""

from __future__ import annotations

import csv
import hashlib
import tarfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "manuscript_vsi_biomedical_data"
ARCHIVE = ROOT / f"{PACKAGE}_20260531.tar.gz"
MD_OUT = ROOT / "reports" / "vsi_archive_integrity_audit_20260531.md"
CSV_OUT = ROOT / "reports" / "vsi_archive_integrity_audit_20260531.csv"

EXPECTED_FILES = [
    "Makefile",
    "README",
    "README.md",
    "author_submission_info_needed.md",
    "author_declaration_signoff_form.md",
    "cas-common.sty",
    "cas-model2-names.bst",
    "cas-sc.cls",
    "citation_metadata_audit.md",
    "reference_identifier_audit.md",
    "reference_publisher_verification_packet.md",
    "reference_online_metadata_audit.md",
    "reference_publisher_signoff_form.md",
    "cover_letter.txt",
    "current_experiment_paper_draft_20260601.md",
    "credit_author_statement.txt",
    "data_availability_statement.txt",
    "declaration_of_interest.txt",
    "editorial_manager_upload_index.md",
    "external_validity_public_data_audit.md",
    "validation_split_leakage_audit.md",
    "figure_privacy_integrity_audit.md",
    "clinical_overlay_visual_review_packet.md",
    "clinical_overlay_ai_visual_prescreen.md",
    "clinical_overlay_signoff_form.md",
    "final_submission_handoff.md",
    "frontier_recommendation_traceability.md",
    "generative_ai_statement.txt",
    "graphical_abstract_description.txt",
    "highlights.tex",
    "human_completion_quickstart.md",
    "initial_draft_delivery_handoff.md",
    "main.tex",
    "main.pdf",
    "manifest.txt",
    "metadata_application_plan.md",
    "metadata_pipeline_dry_run_audit.md",
    "objective_completion_audit.md",
    "official_requirements_snapshot.md",
    "package_consistency_audit.md",
    "pdf_compilation_handoff.md",
    "pdf_render_audit.md",
    "rendered_pdf_visual_prescreen.md",
    "rendered_pdf_author_signoff_form.md",
    "peer_review_risk_audit.md",
    "references.bib",
    "reproducibility_manifest.md",
    "source_evidence_manifest.md",
    "source_layout_audit.md",
    "tex_compile_readiness_audit.md",
    "submission_blocker_audit.md",
    "submission_checklist.md",
    "submission_metadata_author_fill_form.md",
    "submission_metadata_completion_packet.md",
    "submission_metadata_fill_form_sync.md",
    "submission_metadata_preflight.md",
    "submission_metadata_lock_audit.md",
    "submission_metadata_template.yaml",
    "submission_requirements_traceability.md",
    "latex_template_archive/cas-sc-sample.tex",
    "latex_template_archive/cas-sc-template.tex",
    "figures/baseline_ctv_overlay.png",
    "figures/baseline_oar_overlay.png",
    "figures/graphical_abstract.pdf",
    "figures/graphical_abstract.png",
    "figures/our_sdf_k7_ctv_main_comparison.png",
    "figures/sammed3d_sparse_prompt_k7_ctv_overlay.png",
    "figures/vsi_doctor_prior_diagnostic.pdf",
    "figures/vsi_doctor_prior_diagnostic.png",
    "figures/vsi_main_results_dice.pdf",
    "figures/vsi_main_results_dice.png",
    "figures/vsi_method_workflow.pdf",
    "figures/vsi_method_workflow.png",
    "figures/vsi_prompt_sensitivity_headroom.pdf",
    "figures/vsi_prompt_sensitivity_headroom.png",
    "tables/case_level_robustness.tex",
    "tables/clinical_threshold_failure_audit.tex",
    "tables/core_envelope_ablation.tex",
    "tables/doctor_prior_minisplit.tex",
    "tables/main_results.tex",
    "tables/oar_constraint_sensitivity.tex",
    "tables/oracle_headroom.tex",
    "tables/paired_statistical_comparison.tex",
    "tables/patient_aggregated_paired_comparison.tex",
    "tables/patient_aggregated_robustness.tex",
    "tables/prompt_count_sensitivity.tex",
    "tables/prompt_efficiency_frontier.tex",
    "tables/prompt_strategy_robustness.tex",
]

FORBIDDEN_SUFFIXES = [
    ".aux",
    ".abs",
    ".bbl",
    ".bcf",
    ".blg",
    ".fdb_latexmk",
    ".fls",
    ".lof",
    ".log",
    ".lot",
    ".nav",
    ".out",
    ".pyc",
    ".pyo",
    ".run.xml",
    ".snm",
    ".synctex.gz",
    ".toc",
    ".vrb",
    ".xdv",
]
FORBIDDEN_NAMES = {".DS_Store", "Thumbs.db", "__pycache__", ".ipynb_checkpoints"}
MIN_TABLE_TEX_FILES = 10
MIN_FIGURE_PNG_FILES = 9
MIN_FIGURE_PDF_FILES = 5


def sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def member_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for member in archive.getmembers():
            rows.append(
                {
                    "name": member.name,
                    "type": "file" if member.isfile() else "dir" if member.isdir() else "other",
                    "size": str(member.size),
                    "mode": oct(member.mode),
                }
            )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "type", "size", "mode"])
        writer.writeheader()
        writer.writerows(rows)


def is_forbidden_member(name: str) -> bool:
    parts = PurePosixPath(name).parts
    if any(part in FORBIDDEN_NAMES for part in parts):
        return True
    return any(name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES)


def is_unsafe_member(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return name.startswith("/") or ".." in parts


def relative_member_name(name: str) -> str:
    prefix = PACKAGE + "/"
    if name == PACKAGE:
        return ""
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name


def write_markdown(rows: list[dict[str, str]]) -> None:
    file_rows = [row for row in rows if row["type"] == "file"]
    dir_rows = [row for row in rows if row["type"] == "dir"]
    other_rows = [row for row in rows if row["type"] == "other"]
    member_names = {row["name"] for row in rows}
    file_names = {relative_member_name(row["name"]) for row in file_rows}
    expected_paths = {f"{PACKAGE}/{rel}" for rel in EXPECTED_FILES}
    missing = sorted(rel for rel in EXPECTED_FILES if rel not in file_names)
    forbidden = sorted(row["name"] for row in rows if is_forbidden_member(row["name"]))
    unsafe = sorted(row["name"] for row in rows if is_unsafe_member(row["name"]))
    outside_package = sorted(name for name in member_names if name != PACKAGE and not name.startswith(PACKAGE + "/"))
    unexpected_file_roots = sorted(
        row["name"]
        for row in file_rows
        if row["name"] not in expected_paths
    )
    table_count = sum(rel.startswith("tables/") and rel.endswith(".tex") for rel in file_names)
    png_count = sum(rel.startswith("figures/") and rel.endswith(".png") for rel in file_names)
    pdf_count = sum(rel.startswith("figures/") and rel.endswith(".pdf") for rel in file_names)
    enough_tables = table_count >= MIN_TABLE_TEX_FILES
    enough_pngs = png_count >= MIN_FIGURE_PNG_FILES
    enough_pdfs = pdf_count >= MIN_FIGURE_PDF_FILES
    status = "PASS" if (
        not missing
        and not forbidden
        and not unsafe
        and not outside_package
        and not other_rows
        and enough_tables
        and enough_pngs
        and enough_pdfs
    ) else "FAIL"
    archive_sha = sha256_prefix(ARCHIVE)
    archive_size = ARCHIVE.stat().st_size

    lines = [
        "# Archive Integrity Audit",
        "",
        "This audit validates the dated manuscript tarball after `make -C manuscript_vsi_biomedical_data release`. It is intentionally written outside the tarball to avoid changing the archive hash after inspection.",
        "",
        "## Summary",
        "",
        f"- Archive: `{ARCHIVE.name}`",
        f"- Archive bytes: {archive_size}",
        f"- Archive SHA256 prefix: `{archive_sha}`",
        f"- Archive integrity status: {status}",
        f"- Total members: {len(rows)}",
        f"- File members: {len(file_rows)}",
        f"- Directory members: {len(dir_rows)}",
        f"- Unsupported member types: {len(other_rows)}",
        f"- Expected files checked: {len(EXPECTED_FILES)}",
        f"- Missing expected files: {len(missing)}",
        f"- Forbidden temporary members: {len(forbidden)}",
        f"- Unsafe path members: {len(unsafe)}",
        f"- Members outside package root: {len(outside_package)}",
        f"- Unexpected file members: {len(unexpected_file_roots)}",
        f"- Table TeX files: {table_count} (minimum {MIN_TABLE_TEX_FILES})",
        f"- Figure PNG files: {png_count} (minimum {MIN_FIGURE_PNG_FILES})",
        f"- Figure PDF files: {pdf_count} (minimum {MIN_FIGURE_PDF_FILES})",
        "",
        "## Required File Coverage",
        "",
        "| File | Status |",
        "| --- | --- |",
    ]
    for rel in EXPECTED_FILES:
        lines.append(f"| `{PACKAGE}/{rel}` | {'PASS' if rel in file_names else 'MISSING'} |")

    lines.extend(
        [
            "",
            "## Temporary Artifact Check",
            "",
            "- Forbidden suffixes: " + ", ".join(f"`{item}`" for item in FORBIDDEN_SUFFIXES),
            f"- Forbidden temporary members found: {', '.join(forbidden) if forbidden else 'None'}",
            "",
            "## Path Safety Check",
            "",
            f"- Unsafe absolute or traversal members found: {', '.join(unsafe) if unsafe else 'None'}",
            f"- Members outside package root found: {', '.join(outside_package) if outside_package else 'None'}",
            f"- Unsupported member types found: {', '.join(row['name'] for row in other_rows) if other_rows else 'None'}",
            "",
            "## Interpretation",
            "",
            "- PASS means required package files are present, expected table and figure counts are met, no known temporary files are included, paths are extraction-safe, and all members are under the manuscript package root.",
            "- The archive still is not a real submission until author metadata, ethics/funding language, final PDF compilation, manual clinical image review, and manual reference review are completed. Repeat the official-page recheck if upload occurs after the recorded access date or if either official page changes.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    if not ARCHIVE.exists():
        raise SystemExit(f"Missing archive: {ARCHIVE}")
    rows = member_rows()
    write_csv(rows)
    write_markdown(rows)
    forbidden = [row["name"] for row in rows if is_forbidden_member(row["name"])]
    unsafe = [row["name"] for row in rows if is_unsafe_member(row["name"])]
    file_names = {relative_member_name(row["name"]) for row in rows if row["type"] == "file"}
    missing = [rel for rel in EXPECTED_FILES if rel not in file_names]
    outside_package = [row["name"] for row in rows if row["name"] != PACKAGE and not row["name"].startswith(PACKAGE + "/")]
    other_rows = [row for row in rows if row["type"] == "other"]
    table_count = sum(rel.startswith("tables/") and rel.endswith(".tex") for rel in file_names)
    png_count = sum(rel.startswith("figures/") and rel.endswith(".png") for rel in file_names)
    pdf_count = sum(rel.startswith("figures/") and rel.endswith(".pdf") for rel in file_names)
    status = "PASS" if (
        not missing
        and not forbidden
        and not unsafe
        and not outside_package
        and not other_rows
        and table_count >= MIN_TABLE_TEX_FILES
        and png_count >= MIN_FIGURE_PNG_FILES
        and pdf_count >= MIN_FIGURE_PDF_FILES
    ) else "FAIL"
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(
        "Archive status: "
        f"{status}; missing={len(missing)}; forbidden={len(forbidden)}; "
        f"unsafe={len(unsafe)}; outside={len(outside_package)}; other={len(other_rows)}"
    )
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
