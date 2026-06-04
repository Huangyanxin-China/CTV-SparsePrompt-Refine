#!/usr/bin/env python3
"""Verify the strict no-PDF-assets TeX manuscript project."""

import re
import struct
import sys
from pathlib import Path


ROOT = Path("manuscript_vsi_biomedical_data_tex_project_no_pdf_assets_20260601")
REPORT = Path("reports/no_pdf_assets_tex_project_verification_20260601.md")

REQUIRED_FILES = [
    "main.tex",
    "references.bib",
    "highlights.tex",
    "cas-sc.cls",
    "cas-common.sty",
    "cas-model2-names.bst",
    "manifest.txt",
    "README.md",
    "Makefile",
    "apply_submission_metadata.py",
    "metadata_application_plan_no_pdf_assets_20260601.md",
    "cover_letter.txt",
    "credit_author_statement.txt",
    "data_availability_statement.txt",
    "declaration_of_interest.txt",
    "generative_ai_statement.txt",
    "graphical_abstract_description.txt",
    "author_submission_info_needed.md",
    "editorial_manager_upload_index_no_pdf_assets_20260601.md",
    "submission_metadata_template.yaml",
    "submission_metadata_author_fill_form.md",
    "human_completion_quickstart.md",
    "human_completion_validation_matrix_no_pdf_assets_20260601.md",
    "objective_coverage_audit_no_pdf_assets_20260601.md",
    "frontier_recommendation_traceability_no_pdf_assets_20260601.md",
    "source_package_self_containment_audit_no_pdf_assets_20260601.md",
    "manuscript_source_completeness_audit_no_pdf_assets_20260601.md",
    "human_placeholder_audit_no_pdf_assets_20260601.md",
    "clinical_image_review_packet_no_pdf_assets_20260601.md",
    "reference_publisher_review_packet_no_pdf_assets_20260601.md",
    "author_declaration_signoff_packet_no_pdf_assets_20260601.md",
    "rendered_layout_review_packet_no_pdf_assets_20260601.md",
    "official_requirements_snapshot.md",
    "official_requirements_traceability_no_pdf_assets_20260601.md",
    "source_evidence_manifest.md",
    "submission_checklist.md",
    "no_pdf_assets_project_audit.md",
    "no_pdf_assets_manifest.sha256",
    "verify_project.py",
]

REQUIRED_TABLES = [
    "case_level_robustness.tex",
    "clinical_threshold_failure_audit.tex",
    "core_envelope_ablation.tex",
    "doctor_prior_minisplit.tex",
    "main_results.tex",
    "oar_constraint_sensitivity.tex",
    "oracle_headroom.tex",
    "paired_statistical_comparison.tex",
    "patient_aggregated_paired_comparison.tex",
    "patient_aggregated_robustness.tex",
    "prompt_count_sensitivity.tex",
    "prompt_efficiency_frontier.tex",
    "prompt_strategy_robustness.tex",
]

REQUIRED_PNGS = [
    "baseline_ctv_overlay.png",
    "baseline_oar_overlay.png",
    "graphical_abstract.png",
    "our_sdf_k7_ctv_main_comparison.png",
    "sammed3d_sparse_prompt_k7_ctv_overlay.png",
    "vsi_doctor_prior_diagnostic.png",
    "vsi_main_results_dice.png",
    "vsi_method_workflow.png",
    "vsi_prompt_sensitivity_headroom.png",
]

BUILD_ARTIFACT_SUFFIXES = {
    ".aux",
    ".log",
    ".bbl",
    ".blg",
    ".abs",
    ".fls",
    ".fdb_latexmk",
    ".synctex.gz",
    ".pyc",
}


def png_dimensions(path):
    with path.open("rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        length = struct.unpack(">I", handle.read(4))[0]
        chunk_type = handle.read(4)
        if chunk_type != b"IHDR" or length < 8:
            return None
        return struct.unpack(">II", handle.read(8))


def extract_highlights(text):
    return [line.strip()[6:].strip() for line in text.splitlines() if line.strip().startswith(r"\item ")]


def citation_keys(tex):
    keys = set()
    for body in re.findall(r"\\cite\w*\{([^}]+)\}", tex):
        keys.update(item.strip() for item in body.split(",") if item.strip())
    return keys


def bib_keys(text):
    return set(re.findall(r"@\w+\{([^,]+),", text))


def labels(tex):
    return set(re.findall(r"\\label\{([^}]+)\}", tex))


def refs(tex):
    found = set()
    for body in re.findall(r"\\(?:ref|pageref|autoref)\{([^}]+)\}", tex):
        found.update(item.strip() for item in body.split(",") if item.strip())
    return found


def add(checks, name, ok, detail):
    checks.append((name, bool(ok), str(detail)))


def file_has_build_suffix(path):
    text = path.name
    return any(text.endswith(suffix) for suffix in BUILD_ARTIFACT_SUFFIXES)


def main():
    checks = []
    root = ROOT
    tex_path = root / "main.tex"
    bib_path = root / "references.bib"
    highlights_path = root / "highlights.tex"
    trace_path = root / "official_requirements_traceability_no_pdf_assets_20260601.md"
    audit_path = root / "no_pdf_assets_project_audit.md"
    human_matrix_path = root / "human_completion_validation_matrix_no_pdf_assets_20260601.md"
    objective_coverage_path = root / "objective_coverage_audit_no_pdf_assets_20260601.md"
    frontier_trace_path = root / "frontier_recommendation_traceability_no_pdf_assets_20260601.md"
    self_containment_path = root / "source_package_self_containment_audit_no_pdf_assets_20260601.md"
    manuscript_completeness_path = root / "manuscript_source_completeness_audit_no_pdf_assets_20260601.md"
    human_placeholder_path = root / "human_placeholder_audit_no_pdf_assets_20260601.md"
    upload_index_path = root / "editorial_manager_upload_index_no_pdf_assets_20260601.md"

    add(checks, "project directory exists", root.is_dir(), root)
    for rel in REQUIRED_FILES:
        add(checks, f"required file: {rel}", (root / rel).is_file(), root / rel)
    for rel in REQUIRED_TABLES:
        add(checks, f"required table: {rel}", (root / "tables" / rel).is_file(), root / "tables" / rel)
    for rel in REQUIRED_PNGS:
        add(checks, f"required PNG: {rel}", (root / "figures" / rel).is_file(), root / "figures" / rel)

    all_files = list(root.rglob("*")) if root.exists() else []
    pdfs = [path for path in all_files if path.is_file() and path.suffix.lower() == ".pdf"]
    build_artifacts = [path for path in all_files if path.is_file() and file_has_build_suffix(path)]
    cache_dirs = [path for path in root.rglob("__pycache__") if path.is_dir()] if root.exists() else []
    add(checks, "no PDF files in strict project", not pdfs, ", ".join(str(p) for p in pdfs) or "none")
    add(checks, "no LaTeX build artifacts in strict project", not build_artifacts, ", ".join(str(p) for p in build_artifacts) or "none")
    add(checks, "no Python cache directories in strict project", not cache_dirs, ", ".join(str(p) for p in cache_dirs) or "none")

    tex = tex_path.read_text() if tex_path.exists() else ""
    bib = bib_path.read_text() if bib_path.exists() else ""
    highlights = highlights_path.read_text() if highlights_path.exists() else ""
    trace = trace_path.read_text() if trace_path.exists() else ""
    audit = audit_path.read_text() if audit_path.exists() else ""
    human_matrix = human_matrix_path.read_text() if human_matrix_path.exists() else ""
    objective_coverage = objective_coverage_path.read_text() if objective_coverage_path.exists() else ""
    frontier_trace = frontier_trace_path.read_text() if frontier_trace_path.exists() else ""
    self_containment = self_containment_path.read_text() if self_containment_path.exists() else ""
    manuscript_completeness = manuscript_completeness_path.read_text() if manuscript_completeness_path.exists() else ""
    human_placeholder = human_placeholder_path.read_text() if human_placeholder_path.exists() else ""
    clinical_image_packet = (root / "clinical_image_review_packet_no_pdf_assets_20260601.md").read_text() if (root / "clinical_image_review_packet_no_pdf_assets_20260601.md").exists() else ""
    reference_packet = (root / "reference_publisher_review_packet_no_pdf_assets_20260601.md").read_text() if (root / "reference_publisher_review_packet_no_pdf_assets_20260601.md").exists() else ""
    author_declaration_packet = (root / "author_declaration_signoff_packet_no_pdf_assets_20260601.md").read_text() if (root / "author_declaration_signoff_packet_no_pdf_assets_20260601.md").exists() else ""
    rendered_layout_packet = (root / "rendered_layout_review_packet_no_pdf_assets_20260601.md").read_text() if (root / "rendered_layout_review_packet_no_pdf_assets_20260601.md").exists() else ""
    source_evidence = (root / "source_evidence_manifest.md").read_text() if (root / "source_evidence_manifest.md").exists() else ""
    submission_checklist = (root / "submission_checklist.md").read_text() if (root / "submission_checklist.md").exists() else ""
    upload_index = upload_index_path.read_text() if upload_index_path.exists() else ""
    makefile = (root / "Makefile").read_text() if (root / "Makefile").exists() else ""
    metadata_tool = (root / "apply_submission_metadata.py").read_text() if (root / "apply_submission_metadata.py").exists() else ""
    metadata_plan = (root / "metadata_application_plan_no_pdf_assets_20260601.md").read_text() if (root / "metadata_application_plan_no_pdf_assets_20260601.md").exists() else ""

    input_paths = [
        root / (body if body.endswith(".tex") else f"{body}.tex")
        for body in re.findall(r"\\input\{([^}]+)\}", tex)
    ]
    input_text = "\n".join(path.read_text() for path in input_paths if path.exists())
    graphic_paths = [
        root / body
        for body in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", tex)
    ]
    add(checks, "all TeX input files exist", all(path.exists() for path in input_paths), ", ".join(str(p) for p in input_paths))
    add(checks, "all included graphics exist", all(path.exists() for path in graphic_paths), ", ".join(str(p) for p in graphic_paths))
    add(checks, "included graphics are PNG-only", all(path.suffix.lower() == ".png" for path in graphic_paths), ", ".join(path.name for path in graphic_paths))

    used_cites = citation_keys(tex)
    available_bib = bib_keys(bib)
    missing_cites = sorted(used_cites - available_bib)
    add(checks, "all cited BibTeX keys exist", not missing_cites, ", ".join(missing_cites) or "none")

    missing_refs = sorted(refs(tex) - labels(tex + "\n" + input_text))
    add(checks, "all TeX references have labels", not missing_refs, ", ".join(missing_refs) or "none")

    bullets = extract_highlights(highlights)
    bullet_lengths = [len(item) for item in bullets]
    add(checks, "highlights count is 3 to 5", 3 <= len(bullets) <= 5, f"{len(bullets)} bullets")
    add(checks, "each highlight <= 85 characters", all(length <= 85 for length in bullet_lengths), ", ".join(str(v) for v in bullet_lengths))

    keyword_match = re.search(r"\\begin\{keywords\}(.*?)\\end\{keywords\}", tex, re.S)
    keyword_count = 0
    if keyword_match:
        keyword_count = len([item.strip() for item in keyword_match.group(1).split(r"\sep") if item.strip()])
    add(checks, "keyword count is 1 to 7", 1 <= keyword_count <= 7, f"{keyword_count} keywords")

    abstract_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    abstract_words = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", abstract_match.group(1))) if abstract_match else 0
    add(checks, "abstract present", abstract_words > 0, f"{abstract_words} words")

    graphical = root / "figures" / "graphical_abstract.png"
    dims = png_dimensions(graphical) if graphical.exists() else None
    add(checks, "graphical abstract PNG dimensions readable", dims is not None, dims or "missing")
    if dims:
        width, height = dims
        add(checks, "graphical abstract meets minimum pixel area", width >= 1328 and height >= 531, f"{width}x{height}")

    required_tex_markers = [
        r"\documentclass[a4paper,12pt,fleqn,review]{cas-sc}",
        r"\doublespacing",
        r"\linenumbers",
        r"\begin{abstract}",
        r"\begin{keywords}",
        r"\bibliographystyle{cas-model2-names}",
        r"\bibliography{references}",
        r"\section*{Ethics Statement}",
        r"\section*{Data Availability}",
        r"\section*{Declaration of Competing Interest}",
        r"\section*{CRediT Author Statement}",
        r"\section*{Declaration of Generative AI",
        r"\section*{Acknowledgements}",
    ]
    for marker in required_tex_markers:
        add(checks, f"main.tex marker: {marker}", marker in tex, marker)

    required_section_markers = [
        r"\section{Introduction}",
        r"\section{Related Work}",
        r"\section{Materials and Methods}",
        r"\section{Experiments}",
        r"\section{Results}",
        r"\section{Discussion}",
        r"\section{Conclusion}",
    ]
    for marker in required_section_markers:
        add(checks, f"main.tex section marker: {marker}", marker in tex, marker)

    required_trace_markers = [
        "VSI: PR_Biomedical Data",
        "20-35 page",
        "Highlights mandatory",
        "Graphical abstract image size",
        "No generated PDF or build artifacts",
        "HUMAN_METADATA_PLACEHOLDER",
    ]
    for marker in required_trace_markers:
        add(checks, f"traceability marker: {marker}", marker in trace, marker)

    required_audit_markers = [
        "NO_PDF_ASSETS_TEX_PROJECT_READY_WITH_HUMAN_METADATA_PLACEHOLDERS",
        "make verify",
        "Return code: 0",
        "Rendered page count recorded by the TeX log: 23 pages",
        "no-PDF-assets directory",
    ]
    for marker in required_audit_markers:
        add(checks, f"project audit marker: {marker}", marker in audit, marker)

    required_human_matrix_markers = [
        "HUMAN_COMPLETION_REQUIRED_BEFORE_REAL_SUBMISSION",
        "31 scan-level test scans from 21 unique patients",
        "patient-mean rows",
        "Doctor-prior graph refinement is diagnostic future work",
        "sparse-prompted SDF core-envelope CTV completion",
        "make verify",
    ]
    for marker in required_human_matrix_markers:
        add(checks, f"human completion matrix marker: {marker}", marker in human_matrix, marker)

    required_objective_coverage_markers = [
        "OBJECTIVE_COVERAGE_AUDIT_COMPLETE_FOR_SOURCE_PACKAGE",
        "NOT_COMPLETE_FOR_REAL_SUBMISSION",
        "NO_PDF_ASSETS_TEX_PROJECT_READY",
        "VSI: PR_Biomedical Data",
        "frontier_recommendation_traceability_no_pdf_assets_20260601.md",
        "31 scan-level test scans from 21 unique patients",
        "sparse-prompted SDF core-envelope CTV completion",
        "author metadata",
        "ethics",
        "funding",
        "CRediT",
    ]
    for marker in required_objective_coverage_markers:
        add(checks, f"objective coverage marker: {marker}", marker in objective_coverage, marker)

    required_frontier_trace_markers = [
        "FRONTIER_TRACEABILITY_SOURCE_PACKAGE_PASS",
        "PASS_WITH_CONTROLLED_FUTURE_WORK",
        "Recommendations audited: 12",
        "Missing recommendation links: 0",
        "sparse-prompted SDF core-envelope CTV completion",
        "doctor-prior graph refinement remains future work",
        "31 scan-level test scans from 21 unique patients",
        "CONTROLLED_NEGATIVE",
    ]
    for marker in required_frontier_trace_markers:
        add(checks, f"frontier trace marker: {marker}", marker in frontier_trace, marker)

    required_self_containment_markers = [
        "SOURCE_PACKAGE_SELF_CONTAINED_FOR_TEX_AND_SOURCE_VERIFICATION",
        "OFFICIAL_WEB_RECHECK_RECORDED_2026_06_01",
        "NO_PDF_SOURCE_PACKAGE_SELF_CONTAINMENT_PASS",
        "VSI: PR_Biomedical Data",
        "2026-02-01 to 2026-08-31",
        "single-column, double-spaced",
        "main.tex",
        "verify_project.py",
        "upstream experiment reports",
        "not required for extracted TeX compilation",
        "full-package-only human completion commands",
    ]
    for marker in required_self_containment_markers:
        add(checks, f"self-containment marker: {marker}", marker in self_containment, marker)

    required_source_evidence_boundary_markers = [
        "SOURCE_EVIDENCE_PATH_BOUNDARY",
        "Package-local source files",
        "Upstream experiment provenance paths",
        "not required for extracted TeX compilation",
        "source upload assembly",
        "human_placeholder_audit_no_pdf_assets_20260601.md",
        "metadata_application_plan_no_pdf_assets_20260601.md",
        "clinical_image_review_packet_no_pdf_assets_20260601.md",
        "reference_publisher_review_packet_no_pdf_assets_20260601.md",
        "author_declaration_signoff_packet_no_pdf_assets_20260601.md",
        "rendered_layout_review_packet_no_pdf_assets_20260601.md",
        "CLINICAL_IMAGE_SIGNOFF_REQUIRED",
        "REFERENCE_PUBLISHER_SIGNOFF_REQUIRED",
        "AUTHOR_DECLARATION_SIGNOFF_REQUIRED",
        "RENDERED_LAYOUT_SIGNOFF_REQUIRED",
    ]
    for marker in required_source_evidence_boundary_markers:
        add(checks, f"source evidence boundary marker: {marker}", marker in source_evidence, marker)

    required_metadata_plan_markers = [
        "NO_PDF_PACKAGE_LOCAL_METADATA_TOOL",
        "METADATA_APPLICATION_BLOCKED_BY_PLACEHOLDERS",
        "python apply_submission_metadata.py --apply",
        "make metadata-plan",
        "make metadata-apply",
        "main.tex",
        "cover_letter.txt",
        "credit_author_statement.txt",
        "Blocking metadata fields: 21",
    ]
    for marker in required_metadata_plan_markers:
        add(checks, f"metadata application plan marker: {marker}", marker in metadata_plan, marker)

    required_metadata_tool_markers = [
        "submission_metadata_template.yaml",
        "metadata_application_plan_no_pdf_assets_20260601.md",
        "NO_PDF_PACKAGE_LOCAL_METADATA_TOOL",
        "--apply",
        "METADATA_APPLICATION_BLOCKED_BY_PLACEHOLDERS",
        "METADATA_READY_TO_APPLY",
        "METADATA_APPLIED_TO_SOURCE_FILES",
        "Refusing to apply metadata",
    ]
    for marker in required_metadata_tool_markers:
        add(checks, f"metadata tool marker: {marker}", marker in metadata_tool, marker)

    required_manuscript_completeness_markers = [
        "MANUSCRIPT_SOURCE_COMPLETENESS_PASS_WITH_HUMAN_METADATA_PLACEHOLDERS",
        "CLOSED_LOOP_MANUSCRIPT_SOURCE_PASS",
        "Sparse-prompted SDF core-envelope CTV completion",
        "31 scan-level test scans from 21 unique patients",
        "13 editable table inputs",
        "7 manuscript figure inputs",
        "doctor-prior graph refinement remains future work",
        "Ethics Statement",
        "Data Availability",
        "CRediT Author Statement",
        "Declaration of Generative AI",
    ]
    for marker in required_manuscript_completeness_markers:
        add(checks, f"manuscript completeness marker: {marker}", marker in manuscript_completeness, marker)

    required_human_placeholder_markers = [
        "HUMAN_PLACEHOLDER_AUDIT_READY",
        "HUMAN_PLACEHOLDERS_REQUIRED_BEFORE_REAL_SUBMISSION",
        "AUTHOR_METADATA_PLACEHOLDER",
        "ETHICS_IRB_PLACEHOLDER",
        "FUNDING_ACKNOWLEDGEMENTS_PLACEHOLDER",
        "CREDIT_AUTHORSHIP_PLACEHOLDER",
        "CORRESPONDING_AUTHOR_PLACEHOLDER",
        "RENDERED_LAYOUT_SIGNOFF_REQUIRED",
        "CLINICAL_IMAGE_REVIEW_REQUIRED",
        "REFERENCE_PUBLISHER_REVIEW_REQUIRED",
        "VSI: PR_Biomedical Data",
        "NO_PDF_ASSETS_TEX_PROJECT_READY",
        "corresponding.email@institution.edu",
        "Institution to be finalized",
        "Institutional review and consent details must be inserted before submission",
        "Acknowledgements and funding information should be finalized before submission",
        "Final author order and CRediT roles are pending institutional confirmation",
        "author_declaration_signoff_packet_no_pdf_assets_20260601.md",
        "rendered_layout_review_packet_no_pdf_assets_20260601.md",
    ]
    for marker in required_human_placeholder_markers:
        add(checks, f"human placeholder audit marker: {marker}", marker in human_placeholder, marker)

    required_clinical_image_packet_markers = [
        "CLINICAL_IMAGE_REVIEW_PACKET_READY",
        "CLINICAL_IMAGE_SIGNOFF_REQUIRED",
        "FIGURE_PNG_COUNT: 9",
        "FULL_RESOLUTION_PNG_REVIEW_REQUIRED_BEFORE_REAL_SUBMISSION",
        "PENDING_HUMAN_SIGNOFF",
        "figures/graphical_abstract.png",
        "figures/vsi_method_workflow.png",
        "figures/our_sdf_k7_ctv_main_comparison.png",
        "d0978255af0f3cde015dde0609947ff0c02c67e574d34601a0e73c2a14ed7c71",
    ]
    for marker in required_clinical_image_packet_markers:
        add(checks, f"clinical image packet marker: {marker}", marker in clinical_image_packet, marker)

    required_reference_packet_markers = [
        "REFERENCE_PUBLISHER_REVIEW_PACKET_READY",
        "REFERENCE_PUBLISHER_SIGNOFF_REQUIRED",
        "BIBTEX_ENTRY_COUNT: 36",
        "PUBLISHER_RECORD_REVIEW_REQUIRED_BEFORE_REAL_SUBMISSION",
        "PENDING_HUMAN_SIGNOFF",
        "isensee2021nnunet",
        "ravi2024sam2",
        "du2023segvol",
        "maierhein2024metrics",
    ]
    for marker in required_reference_packet_markers:
        add(checks, f"reference publisher packet marker: {marker}", marker in reference_packet, marker)

    required_author_declaration_packet_markers = [
        "AUTHOR_DECLARATION_SIGNOFF_PACKET_READY",
        "AUTHOR_DECLARATION_SIGNOFF_REQUIRED",
        "AUTHOR_DECLARATION_ROW_COUNT: 8",
        "ALL_AUTHOR_APPROVAL_REQUIRED_BEFORE_REAL_SUBMISSION",
        "PENDING_HUMAN_SIGNOFF",
        "declaration_of_interest.txt",
        "generative_ai_statement.txt",
        "data_availability_statement.txt",
        "credit_author_statement.txt",
    ]
    for marker in required_author_declaration_packet_markers:
        add(checks, f"author declaration packet marker: {marker}", marker in author_declaration_packet, marker)

    required_rendered_layout_packet_markers = [
        "RENDERED_LAYOUT_REVIEW_PACKET_READY",
        "RENDERED_LAYOUT_SIGNOFF_REQUIRED",
        "NO_PDF_OUTPUT_INCLUDED",
        "TEMPORARY_COMPILE_PAGE_COUNT: 23",
        "TECTONIC_COMPILE_RETURN_CODE: 0",
        "FINAL_RENDERED_PDF_REVIEW_REQUIRED_AFTER_METADATA_EDITS",
        "PENDING_HUMAN_SIGNOFF",
        "no PDF or build artifacts included",
    ]
    for marker in required_rendered_layout_packet_markers:
        add(checks, f"rendered layout packet marker: {marker}", marker in rendered_layout_packet, marker)

    required_submission_checklist_markers = [
        "NO_PDF_SOURCE_CHECKLIST_READY_WITH_HUMAN_METADATA_PLACEHOLDERS",
        "frontier_recommendation_traceability_no_pdf_assets_20260601.md",
        "source_package_self_containment_audit_no_pdf_assets_20260601.md",
        "manuscript_source_completeness_audit_no_pdf_assets_20260601.md",
        "human_placeholder_audit_no_pdf_assets_20260601.md",
        "clinical_image_review_packet_no_pdf_assets_20260601.md",
        "reference_publisher_review_packet_no_pdf_assets_20260601.md",
        "author_declaration_signoff_packet_no_pdf_assets_20260601.md",
        "rendered_layout_review_packet_no_pdf_assets_20260601.md",
        "metadata_application_plan_no_pdf_assets_20260601.md",
        "apply_submission_metadata.py",
        "No PDF files are included",
        "make metadata-plan",
        "make verify",
        "VSI: PR_Biomedical Data",
    ]
    for marker in required_submission_checklist_markers:
        add(checks, f"submission checklist marker: {marker}", marker in submission_checklist, marker)

    required_upload_index_markers = [
        "SOURCE_UPLOAD_INDEX_READY_WITH_HUMAN_METADATA_PLACEHOLDERS",
        "VSI: PR_Biomedical Data",
        "Candidate Files For Upload",
        "Internal Handoff Files Not Normally Uploaded",
        "main.tex",
        "references.bib",
        "apply_submission_metadata.py",
        "metadata_application_plan_no_pdf_assets_20260601.md",
        "clinical_image_review_packet_no_pdf_assets_20260601.md",
        "reference_publisher_review_packet_no_pdf_assets_20260601.md",
        "author_declaration_signoff_packet_no_pdf_assets_20260601.md",
        "rendered_layout_review_packet_no_pdf_assets_20260601.md",
        "figures/*.png",
        "make verify",
    ]
    for marker in required_upload_index_markers:
        add(checks, f"upload index marker: {marker}", marker in upload_index, marker)

    required_makefile_markers = [
        "verify:",
        "metadata-plan:",
        "metadata-apply:",
        "manifest:",
        "clean-generated:",
        "python verify_project.py",
        "python apply_submission_metadata.py",
        "no_pdf_assets_manifest.sha256",
    ]
    for marker in required_makefile_markers:
        add(checks, f"Makefile marker: {marker}", marker in makefile, marker)

    failures = [item for item in checks if not item[1]]
    status = "PASS" if not failures else "FAIL"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# No-PDF-Assets TeX Project Verification",
        "",
        f"- Project: `{root}`",
        f"- Status: `{status}`",
        f"- Check count: {len(checks)}",
        f"- Failure count: {len(failures)}",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for name, ok, detail in checks:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail.replace('|', '/')} |")
    if failures:
        lines.extend(["", "## Failures", ""])
        for name, _, detail in failures:
            lines.append(f"- {name}: {detail}")
    else:
        lines.extend(["", "All automated no-PDF-assets TeX project checks passed."])
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"Status: {status}")
    print(f"Report: {REPORT}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
