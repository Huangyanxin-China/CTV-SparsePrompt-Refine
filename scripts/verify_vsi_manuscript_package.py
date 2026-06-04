#!/usr/bin/env python3
"""Verify the Pattern Recognition VSI manuscript package.

This checker is intentionally independent of a local TeX installation. It
validates source structure, required auxiliary files, highlights, references,
figures, and known submission blockers. When TeX tools are available it also
reports whether Elsevier's `cas-sc.cls` can be found.
"""

import argparse
import re
import shutil
import subprocess
import struct
from pathlib import Path


REQUIRED_FILES = [
    "main.tex",
    "current_experiment_paper_draft_20260601.md",
    "references.bib",
    "highlights.tex",
    "cover_letter.txt",
    "data_availability_statement.txt",
    "declaration_of_interest.txt",
    "generative_ai_statement.txt",
    "credit_author_statement.txt",
    "submission_checklist.md",
    "submission_metadata_template.yaml",
    "submission_requirements_traceability.md",
    "official_requirements_snapshot.md",
    "reproducibility_manifest.md",
    "editorial_manager_upload_index.md",
    "citation_metadata_audit.md",
    "reference_identifier_audit.md",
    "reference_publisher_verification_packet.md",
    "reference_online_metadata_audit.md",
    "reference_publisher_signoff_form.md",
    "source_layout_audit.md",
    "tex_compile_readiness_audit.md",
    "external_validity_public_data_audit.md",
    "validation_split_leakage_audit.md",
    "frontier_recommendation_traceability.md",
    "objective_completion_audit.md",
    "initial_draft_delivery_handoff.md",
    "metadata_application_plan.md",
    "submission_metadata_completion_packet.md",
    "submission_metadata_author_fill_form.md",
    "submission_metadata_fill_form_sync.md",
    "metadata_pipeline_dry_run_audit.md",
    "package_consistency_audit.md",
    "author_declaration_signoff_form.md",
    "human_completion_quickstart.md",
    "final_submission_handoff.md",
    "pdf_compilation_handoff.md",
    "pdf_render_audit.md",
    "rendered_pdf_visual_prescreen.md",
    "rendered_pdf_author_signoff_form.md",
    "submission_metadata_preflight.md",
    "submission_metadata_lock_audit.md",
    "submission_blocker_audit.md",
    "source_evidence_manifest.md",
    "peer_review_risk_audit.md",
    "author_submission_info_needed.md",
    "graphical_abstract_description.txt",
    "figure_privacy_integrity_audit.md",
    "clinical_overlay_visual_review_packet.md",
    "clinical_overlay_ai_visual_prescreen.md",
    "clinical_overlay_signoff_form.md",
    "README.md",
    "Makefile",
]

LOCAL_LATEX_TEMPLATE_FILES = [
    "cas-sc.cls",
    "cas-common.sty",
    "cas-model2-names.bst",
    "manifest.txt",
]

PLACEHOLDER_PATTERNS = [
    "corresponding.email",
    "Institution to be finalized",
    "city={City}",
    "country={Country}",
    "must be inserted",
    "should be finalized",
    "to be finalized",
    "TODO_REPLACE",
]
KNOWN_TOOL_DIRS = [Path("/tmp/vsi_tectonic_env/bin")]


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text))


def bib_keys(text):
    return set(re.findall(r"@\w+\{([^,]+),", text))


def citation_keys(tex):
    used = set()
    for body in re.findall(r"\\cite\w*\{([^}]+)\}", tex):
        used.update(key.strip() for key in body.split(",") if key.strip())
    return used


def tex_labels(tex):
    return re.findall(r"\\label\{([^}]+)\}", tex)


def tex_refs(tex):
    refs = []
    for body in re.findall(r"\\(?:ref|autoref|pageref)\{([^}]+)\}", tex):
        refs.extend(item.strip() for item in body.split(",") if item.strip())
    return refs


def tex_environments(tex, env):
    pattern = rf"\\begin\{{{re.escape(env)}\}}(.*?)\\end\{{{re.escape(env)}\}}"
    return re.findall(pattern, tex, re.S)


def keyword_count(tex):
    match = re.search(r"\\begin\{keywords\}(.*?)\\end\{keywords\}", tex, re.S)
    if not match:
        return 0
    return len([item.strip() for item in match.group(1).split(r"\sep") if item.strip()])


def title_text(tex):
    match = re.search(r"\\title(?:\[[^]]*\])?\{(.*?)\}", tex, re.S)
    if not match:
        return ""
    text = re.sub(r"\\[A-Za-z]+(?:\[[^]]*\])?(?:\{([^{}]*)\})?", r"\1", match.group(1))
    text = re.sub(r"[{}$]", "", text)
    return " ".join(text.split())


def png_dimensions(path):
    try:
        with path.open("rb") as handle:
            signature = handle.read(8)
            if signature != b"\x89PNG\r\n\x1a\n":
                return None
            length = struct.unpack(">I", handle.read(4))[0]
            chunk_type = handle.read(4)
            if chunk_type != b"IHDR" or length < 8:
                return None
            width, height = struct.unpack(">II", handle.read(8))
            return width, height
    except OSError:
        return None


def check_tool(name):
    found = shutil.which(name)
    if found:
        return found
    for directory in KNOWN_TOOL_DIRS:
        candidate = directory / name
        if candidate.exists():
            return str(candidate)
    return ""


def accepted_tex_backend():
    latexmk = check_tool("latexmk")
    if latexmk:
        return "latexmk", latexmk
    tectonic = check_tool("tectonic")
    if tectonic:
        return "tectonic", tectonic
    return "none", ""


def kpsewhich_file(filename):
    kpsewhich = check_tool("kpsewhich")
    if not kpsewhich:
        return ""
    try:
        result = subprocess.run(
            [kpsewhich, filename],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def add(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})


def verify(root):
    root = Path(root)
    checks = []
    warnings = []
    blockers = []

    for rel in REQUIRED_FILES:
        add(checks, f"required file: {rel}", (root / rel).exists(), root / rel)
    for rel in LOCAL_LATEX_TEMPLATE_FILES:
        add(checks, f"local Elsevier CAS file: {rel}", (root / rel).exists(), root / rel)

    main_path = root / "main.tex"
    tex = main_path.read_text() if main_path.exists() else ""
    refs = (root / "references.bib").read_text() if (root / "references.bib").exists() else ""
    highlights = (root / "highlights.tex").read_text() if (root / "highlights.tex").exists() else ""
    cover_letter = (root / "cover_letter.txt").read_text() if (root / "cover_letter.txt").exists() else ""
    submission_checklist = (root / "submission_checklist.md").read_text() if (root / "submission_checklist.md").exists() else ""
    genai = (root / "generative_ai_statement.txt").read_text() if (root / "generative_ai_statement.txt").exists() else ""
    credit = (root / "credit_author_statement.txt").read_text() if (root / "credit_author_statement.txt").exists() else ""
    traceability = (root / "submission_requirements_traceability.md").read_text() if (root / "submission_requirements_traceability.md").exists() else ""
    official_snapshot = (root / "official_requirements_snapshot.md").read_text() if (root / "official_requirements_snapshot.md").exists() else ""
    reproducibility = (root / "reproducibility_manifest.md").read_text() if (root / "reproducibility_manifest.md").exists() else ""
    upload_index = (root / "editorial_manager_upload_index.md").read_text() if (root / "editorial_manager_upload_index.md").exists() else ""
    citation_audit = (root / "citation_metadata_audit.md").read_text() if (root / "citation_metadata_audit.md").exists() else ""
    refid_audit = (root / "reference_identifier_audit.md").read_text() if (root / "reference_identifier_audit.md").exists() else ""
    ref_publisher_packet = (root / "reference_publisher_verification_packet.md").read_text() if (root / "reference_publisher_verification_packet.md").exists() else ""
    ref_online_audit = (root / "reference_online_metadata_audit.md").read_text() if (root / "reference_online_metadata_audit.md").exists() else ""
    ref_signoff_form = (root / "reference_publisher_signoff_form.md").read_text() if (root / "reference_publisher_signoff_form.md").exists() else ""
    figure_audit = (root / "figure_privacy_integrity_audit.md").read_text() if (root / "figure_privacy_integrity_audit.md").exists() else ""
    overlay_review_packet = (root / "clinical_overlay_visual_review_packet.md").read_text() if (root / "clinical_overlay_visual_review_packet.md").exists() else ""
    overlay_ai_prescreen = (root / "clinical_overlay_ai_visual_prescreen.md").read_text() if (root / "clinical_overlay_ai_visual_prescreen.md").exists() else ""
    overlay_signoff_form = (root / "clinical_overlay_signoff_form.md").read_text() if (root / "clinical_overlay_signoff_form.md").exists() else ""
    layout_audit = (root / "source_layout_audit.md").read_text() if (root / "source_layout_audit.md").exists() else ""
    tex_audit = (root / "tex_compile_readiness_audit.md").read_text() if (root / "tex_compile_readiness_audit.md").exists() else ""
    external_validity_audit = (root / "external_validity_public_data_audit.md").read_text() if (root / "external_validity_public_data_audit.md").exists() else ""
    split_leakage_audit = (root / "validation_split_leakage_audit.md").read_text() if (root / "validation_split_leakage_audit.md").exists() else ""
    frontier_traceability = (root / "frontier_recommendation_traceability.md").read_text() if (root / "frontier_recommendation_traceability.md").exists() else ""
    objective_completion_audit = (root / "objective_completion_audit.md").read_text() if (root / "objective_completion_audit.md").exists() else ""
    initial_draft_delivery_handoff = (root / "initial_draft_delivery_handoff.md").read_text() if (root / "initial_draft_delivery_handoff.md").exists() else ""
    initial_markdown_draft = (root / "current_experiment_paper_draft_20260601.md").read_text() if (root / "current_experiment_paper_draft_20260601.md").exists() else ""
    metadata_application_plan = (root / "metadata_application_plan.md").read_text() if (root / "metadata_application_plan.md").exists() else ""
    metadata_completion_packet = (root / "submission_metadata_completion_packet.md").read_text() if (root / "submission_metadata_completion_packet.md").exists() else ""
    metadata_author_fill_form = (root / "submission_metadata_author_fill_form.md").read_text() if (root / "submission_metadata_author_fill_form.md").exists() else ""
    metadata_fill_form_sync = (root / "submission_metadata_fill_form_sync.md").read_text() if (root / "submission_metadata_fill_form_sync.md").exists() else ""
    package_consistency_audit = (root / "package_consistency_audit.md").read_text() if (root / "package_consistency_audit.md").exists() else ""
    final_submission_handoff = (root / "final_submission_handoff.md").read_text() if (root / "final_submission_handoff.md").exists() else ""
    pdf_compilation_handoff = (root / "pdf_compilation_handoff.md").read_text() if (root / "pdf_compilation_handoff.md").exists() else ""
    pdf_render_audit = (root / "pdf_render_audit.md").read_text() if (root / "pdf_render_audit.md").exists() else ""
    rendered_pdf_visual_prescreen = (root / "rendered_pdf_visual_prescreen.md").read_text() if (root / "rendered_pdf_visual_prescreen.md").exists() else ""
    rendered_pdf_author_signoff_form = (root / "rendered_pdf_author_signoff_form.md").read_text() if (root / "rendered_pdf_author_signoff_form.md").exists() else ""
    author_declaration_signoff_form = (root / "author_declaration_signoff_form.md").read_text() if (root / "author_declaration_signoff_form.md").exists() else ""
    metadata_preflight = (root / "submission_metadata_preflight.md").read_text() if (root / "submission_metadata_preflight.md").exists() else ""
    metadata_lock_audit = (root / "submission_metadata_lock_audit.md").read_text() if (root / "submission_metadata_lock_audit.md").exists() else ""
    blocker_audit = (root / "submission_blocker_audit.md").read_text() if (root / "submission_blocker_audit.md").exists() else ""
    source_evidence_manifest = (root / "source_evidence_manifest.md").read_text() if (root / "source_evidence_manifest.md").exists() else ""
    prompt_efficiency_table = (root / "tables" / "prompt_efficiency_frontier.tex").read_text() if (root / "tables" / "prompt_efficiency_frontier.tex").exists() else ""
    patient_paired_table = (root / "tables" / "patient_aggregated_paired_comparison.tex").read_text() if (root / "tables" / "patient_aggregated_paired_comparison.tex").exists() else ""
    patient_robustness_table = (root / "tables" / "patient_aggregated_robustness.tex").read_text() if (root / "tables" / "patient_aggregated_robustness.tex").exists() else ""
    makefile = (root / "Makefile").read_text() if (root / "Makefile").exists() else ""
    project_root = root.parent if root.parent != Path("") else Path(".")
    clinical_threshold_audit_path = project_root / "reports" / "vsi_clinical_threshold_failure_audit_20260531.md"
    clinical_threshold_audit = clinical_threshold_audit_path.read_text() if clinical_threshold_audit_path.exists() else ""
    patient_paired_report_path = project_root / "reports" / "vsi_patient_aggregated_paired_comparison_20260601.md"
    patient_paired_report = patient_paired_report_path.read_text() if patient_paired_report_path.exists() else ""
    patient_robustness_report_path = project_root / "reports" / "vsi_patient_aggregated_robustness_20260601.md"
    patient_robustness_report = patient_robustness_report_path.read_text() if patient_robustness_report_path.exists() else ""
    prompt_efficiency_report_path = project_root / "reports" / "vsi_prompt_efficiency_frontier_20260531.md"
    prompt_efficiency_report = prompt_efficiency_report_path.read_text() if prompt_efficiency_report_path.exists() else ""

    add(checks, "uses Elsevier single-column 12pt cas-sc review class", r"\documentclass[a4paper,12pt,fleqn,review]{cas-sc}" in tex, "cas-sc 12pt review")
    add(checks, "double spacing enabled", r"\doublespacing" in tex, "setspace")
    add(checks, "line numbers enabled", r"\linenumbers" in tex, "lineno")
    add(checks, "numeric natbib mode enabled", r"\usepackage[numbers,sort&compress]{natbib}" in tex, "natbib numbers")
    add(checks, "CAS bibliography style selected", r"\bibliographystyle{cas-model2-names}" in tex, "cas-model2-names")
    add(checks, "keywords environment present", r"\begin{keywords}" in tex and r"\end{keywords}" in tex, "keywords")
    n_keywords = keyword_count(tex)
    add(checks, "1-7 keywords", 1 <= n_keywords <= 7, f"{n_keywords} keywords")
    add(checks, "competing interest statement present", "Declaration of Competing Interest" in tex, "main.tex")
    add(checks, "data availability statement present", "Data Availability" in tex, "main.tex")
    add(checks, "CRediT author statement present", "credit" in tex.lower() or "credit" in credit.lower(), "main.tex or credit_author_statement.txt")
    add(checks, "generative AI declaration present", "generative ai" in tex.lower() or "generative ai" in genai.lower(), "main.tex or generative_ai_statement.txt")

    abstract_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    abstract_text = abstract_match.group(1) if abstract_match else ""
    abstract_words = word_count(abstract_text) if abstract_match else 0
    add(checks, "abstract present", abstract_match is not None, f"{abstract_words} words")
    add(checks, "abstract <= 250 words", 0 < abstract_words <= 250, f"{abstract_words} words")
    add(checks, "abstract records scan-level 31-scan/21-patient boundary", "31 scan-level test scans from 21 patients" in abstract_text, "scan-level cohort boundary")
    abstract_text_lower = abstract_text.lower()
    add(checks, "abstract records patient-mean paired comparison", "patient-mean paired comparisons" in abstract_text_lower and "all 21 patients" in abstract_text_lower, "patient-mean paired comparison")

    title = title_text(tex)
    add(checks, "title present", bool(title), title)
    add(checks, "title <= 15 words", 0 < word_count(title) <= 15, f"{word_count(title)} words")

    items = [line.replace(r"\item", "").strip() for line in highlights.splitlines() if line.strip().startswith(r"\item")]
    highlight_text = "\n".join(items)
    add(checks, "3-5 highlights", 3 <= len(items) <= 5, f"{len(items)} highlights")
    for idx, item in enumerate(items, 1):
        add(checks, f"highlight {idx} <= 85 chars", len(item) <= 85, f"{len(item)} chars")
    add(checks, "highlights record 31-scan/21-patient boundary", "31 scans from 21 patients" in highlight_text, "scan/patient boundary")
    add(checks, "highlights record patient-mean paired support", "Patient-mean paired tests" in highlight_text and "all 21 patients" in highlight_text, "patient-mean paired support")

    for inp in re.findall(r"\\input\{([^}]+)\}", tex):
        path = root / (inp if inp.endswith(".tex") else inp + ".tex")
        add(checks, f"input exists: {inp}", path.exists(), path)

    tex_sources = {"main.tex": tex}
    for inp in re.findall(r"\\input\{([^}]+)\}", tex):
        path = root / (inp if inp.endswith(".tex") else inp + ".tex")
        if path.exists():
            tex_sources[str(path.relative_to(root))] = path.read_text()
    combined_tex = "\n".join(tex_sources.values())

    for fig in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", tex):
        path = root / fig
        add(checks, f"figure exists: {fig}", path.exists(), path)

    labels = tex_labels(combined_tex)
    duplicate_labels = sorted(label for label in set(labels) if labels.count(label) > 1)
    refs_in_tex = sorted(set(tex_refs(combined_tex)))
    undefined_refs = sorted(set(refs_in_tex) - set(labels))
    unreferenced_labels = sorted(label for label in set(labels) if label.startswith(("fig:", "tab:")) and label not in set(refs_in_tex))
    add(checks, "no duplicate TeX labels", not duplicate_labels, ", ".join(duplicate_labels) if duplicate_labels else f"{len(labels)} labels")
    add(checks, "all TeX refs resolve to labels", not undefined_refs, ", ".join(undefined_refs) if undefined_refs else f"{len(refs_in_tex)} refs")
    add(checks, "all figure/table labels are referenced", not unreferenced_labels, ", ".join(unreferenced_labels) if unreferenced_labels else "all referenced")

    figure_envs = tex_environments(tex, "figure")
    table_envs = tex_environments(combined_tex, "table")
    add(checks, "all figure environments have captions", all(r"\caption" in env for env in figure_envs), f"{len(figure_envs)} figures")
    add(checks, "all table environments have captions", all(r"\caption" in env for env in table_envs), f"{len(table_envs)} tables")

    keys = bib_keys(refs)
    used = citation_keys(tex)
    missing = sorted(used - keys)
    add(checks, "all cited BibTeX keys exist", not missing, ", ".join(missing) if missing else f"{len(used)} citations")
    unused = sorted(keys - used)
    add(checks, "all BibTeX entries are cited", not unused, ", ".join(unused) if unused else f"{len(keys)} entries")
    add(checks, "35-55 references requested by Pattern Recognition", 35 <= len(keys) <= 55, f"{len(keys)} references")

    required_cover_terms = [
        "state of the art",
        "public datasets",
        "validation",
        "VSI: PR_Biomedical Data",
    ]
    for term in required_cover_terms:
        add(checks, f"cover letter mentions: {term}", term.lower() in cover_letter.lower(), term)
    cover_sota_names = ["nnU-Net", "MedSAM", "SAM-Med3D", "LLMSeg", "DeepTarget"]
    found_cover_sota = [name for name in cover_sota_names if name.lower() in cover_letter.lower()]
    add(checks, "cover letter names 5 SOTA articles", len(found_cover_sota) >= 5, ", ".join(found_cover_sota))
    add(
        checks,
        "cover letter discloses scan-level validation cohort",
        (
            "31 scan-level test scans from 21 unique patients" in cover_letter
            or "31 independent test scans from 21 unique patients" in cover_letter
        )
        and "scan-level hold-out" in cover_letter,
        "cover_letter.txt",
    )
    add(
        checks,
        "cover letter avoids patient-external validation overclaim",
        "not a patient-external validation" in cover_letter
        and "fully patient-grouped external validation remains future work" in cover_letter,
        "cover_letter.txt",
    )
    add(
        checks,
        "cover letter states deterministic non-training SDF boundary",
        "deterministic" in cover_letter.lower()
        and "not trained at cohort level" in cover_letter.lower(),
        "cover_letter.txt",
    )

    add(
        checks,
        "traceability audit cites special issue URL",
        "https://www.sciencedirect.com/special-issue/329765" in traceability,
        "submission_requirements_traceability.md",
    )
    add(
        checks,
        "traceability audit cites guide URL",
        "https://www.sciencedirect.com/journal/pattern-recognition/publish/guide-for-authors" in traceability,
        "submission_requirements_traceability.md",
    )
    add(
        checks,
        "traceability audit includes article type",
        "VSI: PR_Biomedical Data" in traceability,
        "submission_requirements_traceability.md",
    )
    add(
        checks,
        "traceability audit records blocker status",
        "| BLOCKER |" in traceability,
        "submission_requirements_traceability.md",
    )
    add(
        checks,
        "official requirements snapshot records status",
        "Snapshot status: OFFICIAL_REQUIREMENTS_RECHECKED_2026_06_01" in official_snapshot,
        "official_requirements_snapshot.md",
    )
    add(
        checks,
        "official requirements snapshot cites special issue URL",
        "https://www.sciencedirect.com/special-issue/329765" in official_snapshot,
        "official_requirements_snapshot.md",
    )
    add(
        checks,
        "official requirements snapshot cites guide URL",
        "https://www.sciencedirect.com/journal/pattern-recognition/publish/guide-for-authors" in official_snapshot,
        "official_requirements_snapshot.md",
    )
    for required_snapshot_item in [
        "Official source URLs: 2",
        "Access date: 2026-06-01 Asia/Shanghai",
        "Source access mode: MANUAL_WEB_REVIEW_AND_OFFLINE_SNAPSHOT",
        "Final official recheck before upload: COMPLETED_ON_2026_06_01",
        "Future upload recheck policy:",
        "VSI: PR_Biomedical Data",
        "ABSTRACT",
        "HIGHLIGHTS",
        "EDITABLE_SOURCE",
        "TITLE_PAGE",
        "FUNDING",
        "AUTHOR_APPROVAL",
        "SUBMISSION_CHECKLIST",
        "BLOCKER",
        "WARNING",
    ]:
        add(
            checks,
            f"official requirements snapshot records: {required_snapshot_item}",
            required_snapshot_item in official_snapshot,
            "official_requirements_snapshot.md",
        )
    add(
        checks,
        "reproducibility manifest cites special issue URL",
        "https://www.sciencedirect.com/special-issue/329765" in reproducibility,
        "reproducibility_manifest.md",
    )
    add(
        checks,
        "reproducibility manifest cites guide URL",
        "https://www.sciencedirect.com/journal/pattern-recognition/publish/guide-for-authors" in reproducibility,
        "reproducibility_manifest.md",
    )
    for section in ["Primary Inputs", "Generation Scripts", "Manuscript Artifacts", "Derived Reports"]:
        add(
            checks,
            f"reproducibility manifest section: {section}",
            f"## {section}" in reproducibility,
            "reproducibility_manifest.md",
        )
    for command in [
        "make -C manuscript_vsi_biomedical_data release",
        "python scripts/create_vsi_manuscript_figures.py",
        "python scripts/create_vsi_figure_privacy_integrity_audit.py",
        "python scripts/create_vsi_clinical_overlay_visual_review_packet.py",
        "python scripts/create_vsi_clinical_overlay_ai_visual_prescreen.py",
        "python scripts/create_vsi_clinical_overlay_signoff_form.py",
        "python scripts/create_vsi_paired_statistical_comparison.py",
        "python scripts/create_vsi_patient_aggregated_paired_comparison.py",
        "python scripts/create_vsi_case_level_robustness_analysis.py",
        "python scripts/create_vsi_patient_aggregated_robustness_analysis.py",
        "python scripts/create_vsi_clinical_threshold_failure_audit.py",
        "python scripts/create_vsi_external_validity_public_data_audit.py",
        "python scripts/create_vsi_validation_split_leakage_audit.py",
        "python scripts/create_vsi_frontier_recommendation_traceability.py",
        "python scripts/create_vsi_official_requirements_snapshot.py",
        "python scripts/create_vsi_initial_draft_delivery_handoff.py",
        "python scripts/create_vsi_objective_completion_audit.py",
        "python scripts/apply_vsi_submission_metadata.py",
        "python scripts/sync_vsi_submission_metadata_from_fill_form.py",
        "python scripts/create_vsi_submission_metadata_completion_packet.py",
        "python scripts/create_vsi_final_submission_handoff.py",
        "python scripts/create_vsi_pdf_compilation_handoff.py",
        "python scripts/create_vsi_pdf_render_audit.py",
        "python scripts/create_vsi_rendered_pdf_visual_prescreen.py",
        "python scripts/create_vsi_rendered_pdf_author_signoff_form.py",
        "python scripts/create_vsi_author_declaration_signoff_form.py",
        "python scripts/create_vsi_prompt_strategy_robustness_analysis.py",
        "python scripts/create_vsi_prompt_efficiency_analysis.py",
        "python scripts/create_vsi_oar_constraint_sensitivity_analysis.py",
        "python scripts/create_vsi_source_layout_audit.py",
        "python scripts/create_vsi_tex_compile_readiness_audit.py",
        "python scripts/create_vsi_submission_metadata_preflight.py",
        "python scripts/create_vsi_submission_metadata_lock_audit.py",
        "python scripts/create_vsi_submission_blocker_audit.py",
        "python scripts/create_vsi_citation_metadata_audit.py",
        "python scripts/create_vsi_reference_identifier_audit.py",
        "python scripts/create_vsi_reference_publisher_verification_packet.py",
        "python scripts/create_vsi_reference_online_metadata_audit.py",
        "python scripts/create_vsi_reference_publisher_signoff_form.py",
        "python scripts/create_vsi_archive_integrity_audit.py",
        "python scripts/verify_vsi_manuscript_package.py",
        "make -C manuscript_vsi_biomedical_data archive",
    ]:
        add(
            checks,
            f"reproducibility manifest command: {command}",
            command in reproducibility,
            "reproducibility_manifest.md",
        )
    add(
        checks,
        "reproducibility manifest has no missing artifacts",
        "MISSING" not in reproducibility,
        "reproducibility_manifest.md",
    )
    add(
        checks,
        "reproducibility manifest records Makefile",
        "manuscript_vsi_biomedical_data/Makefile" in reproducibility,
        "reproducibility_manifest.md",
    )
    add(
        checks,
        "reproducibility manifest records package Markdown initial draft",
        "manuscript_vsi_biomedical_data/current_experiment_paper_draft_20260601.md" in reproducibility,
        "reproducibility_manifest.md",
    )
    add(
        checks,
        "reproducibility manifest records initial draft delivery handoff",
        "manuscript_vsi_biomedical_data/initial_draft_delivery_handoff.md" in reproducibility,
        "reproducibility_manifest.md",
    )
    add(
        checks,
        "reproducibility manifest records metadata fill-form sync audit",
        "manuscript_vsi_biomedical_data/submission_metadata_fill_form_sync.md" in reproducibility,
        "reproducibility_manifest.md",
    )
    add(
        checks,
        "reproducibility manifest records author declaration signoff form",
        "manuscript_vsi_biomedical_data/author_declaration_signoff_form.md" in reproducibility,
        "reproducibility_manifest.md",
    )
    for required_prompt_efficiency_item in [
        "scripts/create_vsi_prompt_efficiency_analysis.py",
        "manuscript_vsi_biomedical_data/tables/prompt_efficiency_frontier.tex",
        "reports/vsi_prompt_efficiency_frontier_20260531.csv",
        "reports/vsi_prompt_efficiency_frontier_20260531.md",
    ]:
        add(
            checks,
            f"reproducibility manifest records prompt-efficiency item: {required_prompt_efficiency_item}",
            required_prompt_efficiency_item in reproducibility,
            "reproducibility_manifest.md",
        )
    for required_patient_paired_item in [
        "scripts/create_vsi_patient_aggregated_paired_comparison.py",
        "manuscript_vsi_biomedical_data/tables/patient_aggregated_paired_comparison.tex",
        "reports/vsi_patient_aggregated_paired_comparison_20260601.csv",
        "reports/vsi_patient_aggregated_paired_comparison_20260601.md",
    ]:
        add(
            checks,
            f"reproducibility manifest records patient-paired item: {required_patient_paired_item}",
            required_patient_paired_item in reproducibility,
            "reproducibility_manifest.md",
        )
    for required_patient_robustness_item in [
        "scripts/create_vsi_patient_aggregated_robustness_analysis.py",
        "manuscript_vsi_biomedical_data/tables/patient_aggregated_robustness.tex",
        "reports/vsi_patient_aggregated_robustness_20260601.csv",
        "reports/vsi_patient_aggregated_robustness_20260601.md",
    ]:
        add(
            checks,
            f"reproducibility manifest records patient-robustness item: {required_patient_robustness_item}",
            required_patient_robustness_item in reproducibility,
            "reproducibility_manifest.md",
        )
    add(
        checks,
        "Markdown initial draft records current-experiment draft status",
        "Draft status: initial manuscript draft based on current completed experiments" in initial_markdown_draft,
        "current_experiment_paper_draft_20260601.md",
    )
    add(
        checks,
        "Markdown initial draft records supported sparse-prompt CTV idea",
        "Sparse-Prompted Multimodal CTV Completion with SDF Core-Envelope Priors" in initial_markdown_draft,
        "current_experiment_paper_draft_20260601.md",
    )
    add(
        checks,
        "initial draft handoff records delivered status",
        "Draft delivery status: INITIAL_DRAFT_DELIVERED" in initial_draft_delivery_handoff,
        "initial_draft_delivery_handoff.md",
    )
    add(
        checks,
        "initial draft handoff records delivered draft files",
        all(
            token in initial_draft_delivery_handoff
            for token in [
                "current_experiment_paper_draft_20260601.md",
                "manuscript_vsi_biomedical_data/main.tex",
                "manuscript_vsi_biomedical_data/main.pdf",
                "manuscript_vsi_biomedical_data_20260531.tar.gz",
            ]
        ),
        "initial_draft_delivery_handoff.md",
    )
    add(
        checks,
        "initial draft handoff preserves human-fill boundary",
        all(
            token.lower() in initial_draft_delivery_handoff.lower()
            for token in [
                "Human-Fill Items for Later Submission",
                "final author list",
                "IRB or ethics committee",
                "Grant numbers",
                "Final PDF signoff",
                "This file closes the requested initial-draft delivery",
            ]
        ),
        "initial_draft_delivery_handoff.md",
    )
    for required_checklist_item in [
        "Package-local Markdown initial draft: `current_experiment_paper_draft_20260601.md`",
        "Initial-draft delivery handoff: `initial_draft_delivery_handoff.md`",
        "make -C manuscript_vsi_biomedical_data initial-draft",
        "INITIAL_DRAFT_DELIVERED",
    ]:
        add(
            checks,
            f"submission checklist records initial-draft item: {required_checklist_item}",
            required_checklist_item in submission_checklist,
            "submission_checklist.md",
        )

    for target in [
        "help",
        "figures",
        "figaudit",
        "overlay-review",
        "overlay-prescreen",
        "overlay-signoff",
        "stats",
        "robustness",
        "clinical",
        "external",
        "split-audit",
        "frontier",
        "official-snapshot",
        "initial-draft",
        "objective",
        "refresh-objective",
        "placement",
        "prompt-efficiency",
        "oar",
        "layout",
        "texcheck",
        "pdf-handoff",
        "pdf-render-audit",
        "pdf-render-compile",
        "pdf-prescreen",
        "pdf-signoff",
        "metadata",
        "metadata-lock",
        "metadata-apply-plan",
        "metadata-packet",
        "metadata-fill-sync",
        "author-signoff",
        "blockers",
        "citations",
        "refids",
        "ref-publisher",
        "ref-online",
        "ref-signoff",
        "ref-online-refresh",
        "handoff",
        "package-consistency",
        "manifest",
        "refresh-manifest",
        "post-objective-manifest",
        "verify",
        "final-verify",
        "post-objective-verify",
        "pycheck",
        "archive",
        "archive-audit",
        "regenerate",
        "release",
    ]:
        add(
            checks,
            f"Makefile target: {target}",
            re.search(rf"^{re.escape(target)}:", makefile, re.M) is not None,
            "Makefile",
        )
    release_match = re.search(r"^release:\s*(.*)$", makefile, re.M)
    release_deps = release_match.group(1).split() if release_match else []
    for dep in ["figures", "figaudit", "overlay-review", "overlay-prescreen", "overlay-signoff", "stats", "robustness", "clinical", "external", "split-audit", "frontier", "official-snapshot", "initial-draft", "placement", "prompt-efficiency", "oar", "layout", "texcheck", "pdf-handoff", "pdf-render-compile", "pdf-prescreen", "pdf-signoff", "metadata", "metadata-lock", "metadata-apply-plan", "metadata-packet", "metadata-fill-sync", "author-signoff", "blockers", "citations", "refids", "ref-publisher", "ref-online", "ref-signoff", "handoff", "objective", "package-consistency", "manifest", "verify", "refresh-manifest", "final-verify", "refresh-objective", "post-objective-manifest", "post-objective-verify", "pycheck", "archive", "archive-audit"]:
        add(
            checks,
            f"Makefile release includes: {dep}",
            dep in release_deps,
            " ".join(release_deps) if release_deps else "missing release target",
        )
    if release_deps:
        ordered_refresh = (
            "verify" in release_deps
            and "refresh-manifest" in release_deps
            and "final-verify" in release_deps
            and release_deps.index("verify") < release_deps.index("refresh-manifest") < release_deps.index("final-verify")
        )
    else:
        ordered_refresh = False
    add(
        checks,
        "Makefile release refreshes manifest between verifier passes",
        ordered_refresh,
        " ".join(release_deps) if release_deps else "missing release target",
    )
    if release_deps:
        ordered_archive_audit = (
            "archive" in release_deps
            and "archive-audit" in release_deps
            and release_deps.index("archive") < release_deps.index("archive-audit")
        )
    else:
        ordered_archive_audit = False
    add(
        checks,
        "Makefile release audits archive after tarball creation",
        ordered_archive_audit,
        " ".join(release_deps) if release_deps else "missing release target",
    )
    add(
        checks,
        "Makefile archive target uses dated package name",
        "manuscript_vsi_biomedical_data_20260531.tar.gz" in makefile or "$(PACKAGE)_20260531.tar.gz" in makefile,
        "Makefile",
    )

    add(
        checks,
        "upload index includes article type",
        "VSI: PR_Biomedical Data" in upload_index,
        "editorial_manager_upload_index.md",
    )
    add(
        checks,
        "upload index records current highlight count",
        f"{len(items)} highlights" in upload_index,
        "editorial_manager_upload_index.md",
    )
    for rel in [
        "main.tex",
        "references.bib",
        "highlights.tex",
        "cover_letter.txt",
        "data_availability_statement.txt",
        "declaration_of_interest.txt",
        "credit_author_statement.txt",
        "generative_ai_statement.txt",
        "citation_metadata_audit.md",
        "reference_identifier_audit.md",
        "reference_publisher_verification_packet.md",
        "reference_online_metadata_audit.md",
        "official_requirements_snapshot.md",
        "current_experiment_paper_draft_20260601.md",
        "figure_privacy_integrity_audit.md",
        "clinical_overlay_visual_review_packet.md",
        "clinical_overlay_ai_visual_prescreen.md",
        "clinical_overlay_signoff_form.md",
        "source_layout_audit.md",
        "tex_compile_readiness_audit.md",
        "external_validity_public_data_audit.md",
        "validation_split_leakage_audit.md",
        "frontier_recommendation_traceability.md",
        "objective_completion_audit.md",
        "initial_draft_delivery_handoff.md",
        "metadata_application_plan.md",
        "submission_metadata_completion_packet.md",
        "submission_metadata_author_fill_form.md",
        "author_declaration_signoff_form.md",
        "final_submission_handoff.md",
        "pdf_compilation_handoff.md",
        "pdf_render_audit.md",
        "rendered_pdf_author_signoff_form.md",
        "submission_metadata_preflight.md",
        "submission_metadata_lock_audit.md",
        "submission_blocker_audit.md",
        "figures/*.png",
        "tables/*.tex",
    ]:
        add(
            checks,
            f"upload index maps file: {rel}",
            rel in upload_index,
            "editorial_manager_upload_index.md",
        )
    for term in ["Author names and order", "Author affiliations", "Corresponding author email/address", "Ethics approval", "Funding statement"]:
        add(
            checks,
            f"upload index metadata blocker: {term}",
            term in upload_index and "BLOCKER" in upload_index,
            "editorial_manager_upload_index.md",
        )
    add(
        checks,
        "upload index includes verifier command",
        "python scripts/verify_vsi_manuscript_package.py" in upload_index,
        "editorial_manager_upload_index.md",
    )
    add(
        checks,
        "upload index includes preferred release command",
        "make -C manuscript_vsi_biomedical_data release" in upload_index,
        "editorial_manager_upload_index.md",
    )
    add(
        checks,
        "upload index includes initial draft generator command",
        "python scripts/create_vsi_initial_draft_delivery_handoff.py" in upload_index,
        "editorial_manager_upload_index.md",
    )
    add(
        checks,
        "citation metadata audit reports 36 entries",
        "Total BibTeX entries: 36" in citation_audit,
        "citation_metadata_audit.md",
    )
    add(
        checks,
        "citation metadata audit has no structural failures",
        "Structural failures: 0" in citation_audit and "| FAIL |" not in citation_audit,
        "citation_metadata_audit.md",
    )
    add(
        checks,
        "citation metadata audit records manual final-review tasks",
        "Remaining Manual Citation Tasks" in citation_audit,
        "citation_metadata_audit.md",
    )
    add(
        checks,
        "reference identifier audit reports 36 entries",
        "Total BibTeX entries: 36" in refid_audit,
        "reference_identifier_audit.md",
    )
    add(
        checks,
        "reference identifier audit has no identifier failures",
        "Identifier failures: 0" in refid_audit and "| FAIL |" not in refid_audit,
        "reference_identifier_audit.md",
    )
    add(
        checks,
        "reference identifier audit records DOI coverage",
        "DOI identifiers: 33" in refid_audit,
        "reference_identifier_audit.md",
    )
    add(
        checks,
        "reference identifier audit records arXiv-only entries",
        "arXiv-only entries: 0" in refid_audit,
        "reference_identifier_audit.md",
    )
    add(
        checks,
        "reference identifier audit keeps release offline",
        "Online resolver checks: NOT RUN BY RELEASE" in refid_audit,
        "reference_identifier_audit.md",
    )
    add(
        checks,
        "reference publisher verification packet reports manual status",
        "Packet status: MANUAL_PUBLISHER_REVIEW_REQUIRED" in ref_publisher_packet,
        "reference_publisher_verification_packet.md",
    )
    add(
        checks,
        "reference publisher verification packet queues 36 entries",
        "Entries queued: 36" in ref_publisher_packet,
        "reference_publisher_verification_packet.md",
    )
    add(
        checks,
        "reference publisher verification packet has no structural failures",
        "Structural failures: 0" in ref_publisher_packet and "STRUCTURAL_REPAIR_REQUIRED" not in ref_publisher_packet,
        "reference_publisher_verification_packet.md",
    )
    add(
        checks,
        "reference publisher verification packet has no identifier failures",
        "Identifier failures: 0" in ref_publisher_packet and "IDENTIFIER_REPAIR_REQUIRED" not in ref_publisher_packet,
        "reference_publisher_verification_packet.md",
    )
    for required_ref_packet_item in [
        "DOI entries: 33",
        "arXiv-only entries: 0",
        "Entries with abbreviated author lists: 0",
        "Online resolver checks: NOT RUN BY RELEASE",
        "reference_online_metadata_audit.md",
        "reference_publisher_signoff_form.md",
        "Completion Rule",
    ]:
        add(
            checks,
            f"reference publisher verification packet records: {required_ref_packet_item}",
            required_ref_packet_item in ref_publisher_packet,
            "reference_publisher_verification_packet.md",
        )
    add(
        checks,
        "reference online metadata audit records status",
        "Online metadata audit status: ONLINE_METADATA_CROSSCHECK_PASS" in ref_online_audit,
        "reference_online_metadata_audit.md",
    )
    for required_ref_online_item in [
        "Entries checked: 36",
        "Metadata fetch failures: 0",
        "Hard review rows: 0",
        "Review warning rows: 0",
        "Title review rows: 0",
        "Year review rows: 0",
        "DOI review rows: 0",
        "Crossref rows: 31",
        "arXiv rows: 2",
        "DataCite rows: 0",
        "PublisherURL rows: 3",
        "Accepted-version review rows: 0",
        "Accepted-version check-recorded rows: 2",
        "Abbreviated-author review rows: 0",
        "Manual publisher verification status: STILL REQUIRED",
        "reference_publisher_verification_packet.md",
        "Crossref",
        "arXiv",
        "PublisherURL",
    ]:
        add(
            checks,
            f"reference online metadata audit records: {required_ref_online_item}",
            required_ref_online_item in ref_online_audit,
            "reference_online_metadata_audit.md",
        )
    add(
        checks,
        "reference publisher signoff form records status",
        "Signoff status: REFERENCE_PUBLISHER_SIGNOFF_REQUIRED" in ref_signoff_form
        or "Signoff status: REFERENCE_PUBLISHER_SIGNOFF_COMPLETE" in ref_signoff_form,
        "reference_publisher_signoff_form.md",
    )
    for required_ref_signoff_item in [
        "Entries requiring signoff: 36",
        "Blocking signoff rows:",
        "Allowed final decisions:",
        "APPROVED_NO_CHANGES",
        "APPROVED_AFTER_BIBTEX_UPDATE",
        "NEEDS_BIBTEX_UPDATE",
        "REJECTED_OR_REPLACE_REFERENCE",
        "Approved final decision:",
        "Reviewer and review date:",
        "Source checked:",
        "Corrections applied to `references.bib`:",
        "reports/vsi_reference_publisher_signoff_20260531.csv",
        "Completion Rule",
    ]:
        add(
            checks,
            f"reference publisher signoff form records: {required_ref_signoff_item}",
            required_ref_signoff_item in ref_signoff_form,
            "reference_publisher_signoff_form.md",
        )
    add(
        checks,
        "figure privacy audit reports figure inventory",
        "Figure files audited: 14" in figure_audit,
        "figure_privacy_integrity_audit.md",
    )
    add(
        checks,
        "figure privacy audit has no filename PHI hits",
        "Filename PHI hits: 0" in figure_audit,
        "figure_privacy_integrity_audit.md",
    )
    add(
        checks,
        "figure privacy audit has no metadata PHI hits",
        "Metadata PHI hits: 0" in figure_audit,
        "figure_privacy_integrity_audit.md",
    )
    add(
        checks,
        "figure privacy audit has no integrity failures",
        "Integrity/metadata failures: 0" in figure_audit,
        "figure_privacy_integrity_audit.md",
    )
    add(
        checks,
        "figure privacy audit preserves manual visual review requirement",
        "Pixel OCR status: NOT RUN" in figure_audit and "Final author visual review status: REQUIRED" in figure_audit,
        "figure_privacy_integrity_audit.md",
    )
    add(
        checks,
        "clinical overlay visual review packet records status",
        "Packet status: CLINICAL_OVERLAY_VISUAL_REVIEW_REQUIRED" in overlay_review_packet,
        "clinical_overlay_visual_review_packet.md",
    )
    add(
        checks,
        "clinical overlay visual review packet queues four files",
        "Clinical overlay files queued: 4" in overlay_review_packet,
        "clinical_overlay_visual_review_packet.md",
    )
    add(
        checks,
        "clinical overlay visual review packet has no missing queued files",
        "Missing or unreadable queued files: 0" in overlay_review_packet,
        "clinical_overlay_visual_review_packet.md",
    )
    add(
        checks,
        "clinical overlay visual review packet carries no metadata PHI hits",
        "Filename PHI hits carried forward: 0" in overlay_review_packet and "Metadata PHI hits carried forward: 0" in overlay_review_packet,
        "clinical_overlay_visual_review_packet.md",
    )
    for required_overlay_item in [
        "Pixel OCR status: NOT RUN BY RELEASE",
        "AI visual prescreen companion: `clinical_overlay_ai_visual_prescreen.md`",
        "Final signoff form: `clinical_overlay_signoff_form.md`",
        "Manual visual review status: REQUIRED",
        "Clinical-owner signoff status: REQUIRED",
        "baseline_ctv_overlay.png",
        "baseline_oar_overlay.png",
        "sammed3d_sparse_prompt_k7_ctv_overlay.png",
        "our_sdf_k7_ctv_main_comparison.png",
        "Completion Rule",
    ]:
        add(
            checks,
            f"clinical overlay visual review packet records: {required_overlay_item}",
            required_overlay_item in overlay_review_packet,
            "clinical_overlay_visual_review_packet.md",
        )
    add(
        checks,
        "clinical overlay AI visual prescreen records status",
        "AI visual prescreen status: AI_VISUAL_PRESCREEN_REVIEWED_WITH_RESIDUAL_OWNER_SIGNOFF_REQUIRED" in overlay_ai_prescreen,
        "clinical_overlay_ai_visual_prescreen.md",
    )
    add(
        checks,
        "clinical overlay AI visual prescreen covers four files",
        "Clinical overlay files prescreened: 4" in overlay_ai_prescreen,
        "clinical_overlay_ai_visual_prescreen.md",
    )
    add(
        checks,
        "clinical overlay AI visual prescreen has no missing files",
        "Missing or unreadable prescreen files: 0" in overlay_ai_prescreen,
        "clinical_overlay_ai_visual_prescreen.md",
    )
    add(
        checks,
        "clinical overlay AI visual prescreen has no visible PHI-like text",
        "Visible PHI-like text after AI prescreen: 0" in overlay_ai_prescreen,
        "clinical_overlay_ai_visual_prescreen.md",
    )
    add(
        checks,
        "clinical overlay AI visual prescreen has no case/date title tokens",
        "Case/date title tokens after anonymization: 0" in overlay_ai_prescreen,
        "clinical_overlay_ai_visual_prescreen.md",
    )
    for required_prescreen_item in [
        "Pixel OCR status: NOT RUN BY RELEASE",
        "Clinical-owner signoff status: STILL REQUIRED",
        "Rendered-PDF clinical overlay review status: STILL REQUIRED AFTER COMPILE",
        "Final signoff form: `clinical_overlay_signoff_form.md`",
        "baseline_ctv_overlay.png",
        "baseline_oar_overlay.png",
        "sammed3d_sparse_prompt_k7_ctv_overlay.png",
        "our_sdf_k7_ctv_main_comparison.png",
        "Completion Rule",
    ]:
        add(
            checks,
            f"clinical overlay AI visual prescreen records: {required_prescreen_item}",
            required_prescreen_item in overlay_ai_prescreen,
            "clinical_overlay_ai_visual_prescreen.md",
        )
    add(
        checks,
        "clinical overlay signoff form records status",
        "Signoff status: CLINICAL_OVERLAY_SIGNOFF_REQUIRED" in overlay_signoff_form
        or "Signoff status: CLINICAL_OVERLAY_SIGNOFF_COMPLETE" in overlay_signoff_form,
        "clinical_overlay_signoff_form.md",
    )
    for required_overlay_signoff_item in [
        "Clinical overlay files requiring signoff: 4",
        "Blocking signoff rows:",
        "Allowed final decisions:",
        "APPROVED_NO_VISIBLE_PHI",
        "APPROVED_AFTER_REDACTION",
        "NEEDS_REDACTION_OR_REGENERATION",
        "REPLACE_OR_REMOVE_FIGURE",
        "Final pixel-review decision:",
        "Reviewer and review date:",
        "Full-resolution PNG checked:",
        "Rendered PDF checked:",
        "Corrections or regeneration notes:",
        "reports/vsi_clinical_overlay_signoff_20260531.csv",
        "clinical_overlay_visual_review_packet.md",
        "clinical_overlay_ai_visual_prescreen.md",
        "Completion Rule",
    ]:
        add(
            checks,
            f"clinical overlay signoff form records: {required_overlay_signoff_item}",
            required_overlay_signoff_item in overlay_signoff_form,
            "clinical_overlay_signoff_form.md",
        )
    add(
        checks,
        "source layout audit records estimated page count",
        "Estimated page count:" in layout_audit,
        "source_layout_audit.md",
    )
    add(
        checks,
        "source layout audit is within 20-35 page target",
        "20-35 pages" in layout_audit and "Source-level status: ESTIMATE_IN_RANGE" in layout_audit,
        "source_layout_audit.md",
    )
    add(
        checks,
        "source layout audit preserves PDF verification warning",
        "PDF page-count status: NOT VERIFIED" in layout_audit,
        "source_layout_audit.md",
    )
    add(
        checks,
        "TeX compile-readiness audit records source status",
        "Source readiness status: SOURCE_CHECKS_PASS" in tex_audit,
        "tex_compile_readiness_audit.md",
    )
    add(
        checks,
        "TeX compile-readiness audit has no source failures",
        "Source-level failure count: 0" in tex_audit and "| FAIL |" not in tex_audit,
        "tex_compile_readiness_audit.md",
    )
    add(
        checks,
        "TeX compile-readiness audit preserves PDF warning",
        "Rendered PDF status: NOT VERIFIED" in tex_audit,
        "tex_compile_readiness_audit.md",
    )
    for required_tex_item in [
        "all input files exist",
        "all included graphics exist",
        "all cited BibTeX keys exist",
        "no duplicate labels",
        "all refs resolve",
        "TeX tool unavailable: pdflatex",
    ]:
        add(
            checks,
            f"TeX compile-readiness audit records: {required_tex_item}",
            required_tex_item in tex_audit,
            "tex_compile_readiness_audit.md",
        )
    add(
        checks,
        "external validity audit records status",
        "Status: PASS_WITH_DISCLOSED_LIMITATION" in external_validity_audit,
        "external_validity_public_data_audit.md",
    )
    add(
        checks,
        "external validity audit has no failed checks",
        "| FAIL |" not in external_validity_audit and "Failing checks: 0" in external_validity_audit,
        "external_validity_public_data_audit.md",
    )
    for required_external_item in [
        "Private institutional cohort disclosed",
        "Public benchmark limitation disclosed",
        "Public generalization claim avoided",
        "Fully automatic CT-to-CTV claim avoided",
        "Validation measures documented",
        "Reproducibility under private-data limits documented",
        "External validity residual risk retained",
    ]:
        add(
            checks,
            f"external validity audit records: {required_external_item}",
            required_external_item in external_validity_audit,
            "external_validity_public_data_audit.md",
        )
    add(
        checks,
        "validation split/leakage audit records status",
        "Status: PASS_WITH_SCAN_LEVEL_LIMITATION" in split_leakage_audit,
        "validation_split_leakage_audit.md",
    )
    add(
        checks,
        "validation split/leakage audit has no failed checks",
        "| FAIL |" not in split_leakage_audit and "Failing checks: 0" in split_leakage_audit,
        "validation_split_leakage_audit.md",
    )
    for required_split_item in [
        "31 scans from 21 unique patients",
        "Scan-level rather than patient-external validation",
        "Proposed SDF method has no cohort-training leakage path",
        "Exact held-out scan overlap absent",
        "Patient-level overlap disclosed",
        "Doctor-prior split is patient grouped",
        "Manuscript claim boundary matches split audit",
    ]:
        add(
            checks,
            f"validation split/leakage audit records: {required_split_item}",
            required_split_item in split_leakage_audit,
            "validation_split_leakage_audit.md",
        )
    add(
        checks,
        "source evidence manifest records validation split/leakage audit",
        "Validation Split and Leakage Boundary Audit" in source_evidence_manifest
        and "validation_split_leakage_audit.md" in source_evidence_manifest
        and "31 scans from 21 unique patients" in source_evidence_manifest,
        "source_evidence_manifest.md",
    )
    add(
        checks,
        "traceability audit records validation split/leakage audit",
        "Validation split and leakage boundaries are centrally auditable" in traceability
        and "PASS_WITH_SCAN_LEVEL_LIMITATION" in traceability,
        "submission_requirements_traceability.md",
    )
    add(
        checks,
        "frontier traceability audit records status",
        "Status: PASS_WITH_CONTROLLED_FUTURE_WORK" in frontier_traceability,
        "frontier_recommendation_traceability.md",
    )
    add(
        checks,
        "frontier traceability audit has no missing recommendation links",
        "Missing recommendation links: 0" in frontier_traceability and "| MISSING |" not in frontier_traceability,
        "frontier_recommendation_traceability.md",
    )
    for required_frontier_item in [
        "sparse-prompted CTV completion",
        "SDF propagation and a core-envelope representation",
        "Benchmark against fully automatic networks and promptable segmentation baselines",
        "Use oracle envelope headroom",
        "Test simple HU/support/OAR refinement",
        "Evaluate the doctor-prior graph idea",
        "Effective closed-loop idea",
    ]:
        add(
            checks,
            f"frontier traceability records: {required_frontier_item}",
            required_frontier_item in frontier_traceability,
            "frontier_recommendation_traceability.md",
        )
    add(
        checks,
        "objective completion audit records current decision",
        "Completion decision: NOT_COMPLETE" in objective_completion_audit or "Completion decision: COMPLETE" in objective_completion_audit,
        "objective_completion_audit.md",
    )
    add(
        checks,
        "objective completion audit preserves active-goal recommendation",
        "Goal status recommendation:" in objective_completion_audit,
        "objective_completion_audit.md",
    )
    for required_objective_item in [
        "Use the frontier literature/project report as the starting point",
        "Conduct further experiments and summarize the effective evidence-backed idea",
        "Deliver the current-experiment initial draft while preserving later human-fill boundaries",
        "Output a complete local TeX manuscript project and archive",
        "Satisfy journal source-format requirements for the TeX project",
        "Finalize author, affiliation, corresponding-author, ethics, funding, CRediT metadata, and author declarations",
        "Compile and inspect the final PDF",
        "Complete clinical overlay pixel PHI review",
        "Recheck official special-issue and guide requirements before real upload",
        "Declare the full original objective complete",
    ]:
        add(
            checks,
            f"objective completion audit records: {required_objective_item}",
            required_objective_item in objective_completion_audit,
            "objective_completion_audit.md",
        )
    add(
        checks,
        "metadata application plan records status",
        "Status: BLOCKED_BY_PLACEHOLDERS" in metadata_application_plan
        or "Status: READY_TO_APPLY" in metadata_application_plan
        or "Status: APPLIED" in metadata_application_plan,
        "metadata_application_plan.md",
    )
    for required_apply_item in [
        "Apply command after final author approval",
        "Files modified: NO",
        "Targets: `main.tex`, `cover_letter.txt`, `credit_author_statement.txt`",
        "No manuscript file is modified unless `--apply` is used",
    ]:
        add(
            checks,
            f"metadata application plan records: {required_apply_item}",
            required_apply_item in metadata_application_plan,
            "metadata_application_plan.md",
        )
    add(
        checks,
        "metadata completion packet records status",
        "Packet status: BLOCKED_BY_REQUIRED_METADATA" in metadata_completion_packet
        or "Packet status: READY_FOR_AUTHOR_REVIEW" in metadata_completion_packet,
        "submission_metadata_completion_packet.md",
    )
    for required_packet_item in [
        "Required metadata blockers:",
        "Human fill form: `submission_metadata_author_fill_form.md`",
        "Fill-form sync dry-run command",
        "Author-approved YAML sync command",
        "authors.0.email",
        "affiliations.0.organization",
        "corresponding_author.email",
        "ethics.approval_body",
        "funding.statement",
        "author_contributions.conceptualization",
        "Dry-run validation command",
        "Author-approved apply command",
        "Field Ownership",
    ]:
        add(
            checks,
            f"metadata completion packet records: {required_packet_item}",
            required_packet_item in metadata_completion_packet,
            "submission_metadata_completion_packet.md",
        )
    add(
        checks,
        "metadata author fill form records purpose and source",
        "Submission Metadata Author Fill Form" in metadata_author_fill_form
        and "submission_metadata_template.yaml" in metadata_author_fill_form,
        "submission_metadata_author_fill_form.md",
    )
    for required_form_item in [
        "Required fields listed:",
        "Required fields still blocked:",
        "Approved final value:",
        "Fill-form sync dry-run command",
        "Author-approved YAML sync command",
        "authors.0.email",
        "ethics.approval_body",
        "funding.statement",
        "author_contributions.conceptualization",
        "make -C manuscript_vsi_biomedical_data metadata metadata-lock metadata-apply-plan",
        "python scripts/apply_vsi_submission_metadata.py --apply",
    ]:
        add(
            checks,
            f"metadata author fill form records: {required_form_item}",
            required_form_item in metadata_author_fill_form,
            "submission_metadata_author_fill_form.md",
        )
    add(
        checks,
        "metadata fill-form sync records status",
        "Sync status: BLOCKED_BY_EMPTY_APPROVED_VALUES" in metadata_fill_form_sync
        or "Sync status: READY_TO_APPLY" in metadata_fill_form_sync
        or "Sync status: APPLIED" in metadata_fill_form_sync,
        "submission_metadata_fill_form_sync.md",
    )
    for required_sync_item in [
        "Apply requested:",
        "YAML modified:",
        "Blocking rows:",
        "Dry-run command: `make -C manuscript_vsi_biomedical_data metadata-fill-sync`",
        "Author-approved YAML sync command: `python scripts/sync_vsi_submission_metadata_from_fill_form.py --apply`",
        "Post-sync validation command",
        "Manuscript propagation command after final author approval",
        "BLOCKER_EMPTY_APPROVED_VALUE",
        "authors.0.email",
        "submission_metadata_template.yaml",
    ]:
        add(
            checks,
            f"metadata fill-form sync records: {required_sync_item}",
            required_sync_item in metadata_fill_form_sync,
            "submission_metadata_fill_form_sync.md",
        )
    add(
        checks,
        "author declaration signoff form records status",
        "Signoff status: AUTHOR_DECLARATION_SIGNOFF_REQUIRED" in author_declaration_signoff_form
        or "Signoff status: AUTHOR_DECLARATION_SIGNOFF_COMPLETE" in author_declaration_signoff_form,
        "author_declaration_signoff_form.md",
    )
    for required_author_signoff_item in [
        "Declaration signoff checklist rows: 12",
        "Blocking signoff rows:",
        "Allowed final decisions:",
        "APPROVED_CONFIRMED",
        "APPROVED_AFTER_UPDATE",
        "NEEDS_METADATA_UPDATE",
        "NEEDS_DECLARATION_UPDATE",
        "NEEDS_AUTHOR_CONFIRMATION",
        "Final declaration decision:",
        "Confirming party and date:",
        "All required authors/authorities covered:",
        "Source or approval record checked:",
        "Corrections or notes:",
        "reports/vsi_author_declaration_signoff_20260601.csv",
        "submission_metadata_author_fill_form.md",
        "submission_metadata_template.yaml",
        "declaration_of_interest.txt",
        "data_availability_statement.txt",
        "generative_ai_statement.txt",
        "credit_author_statement.txt",
        "Completion Rule",
    ]:
        add(
            checks,
            f"author declaration signoff form records: {required_author_signoff_item}",
            required_author_signoff_item in author_declaration_signoff_form,
            "author_declaration_signoff_form.md",
        )
    add(
        checks,
        "final submission handoff records decision",
        "Handoff decision: NOT_READY_FOR_UPLOAD" in final_submission_handoff
        or "Handoff decision: READY_FOR_UPLOAD" in final_submission_handoff,
        "final_submission_handoff.md",
    )
    for required_handoff_item in [
        "Initial draft delivery",
        "Author, ethics, funding, and CRediT metadata",
        "Author-approved metadata application",
        "Author declarations and final approval",
        "author_declaration_signoff_form.md",
        "Rendered PDF compile and inspection",
        "rendered_pdf_author_signoff_form.md",
        "Publisher-record reference review",
        "reference_publisher_signoff_form.md",
        "Clinical figure visual PHI review",
        "clinical_overlay_signoff_form.md",
        "Official special-issue and guide recheck",
        "External validity and claim boundary",
        "Final release archive",
        "Initial draft delivery handoff",
        "submission_metadata_author_fill_form.md",
        "Fill-form YAML sync command after author approval",
        "Final metadata apply command after author approval",
        "Final PDF command in a TeX-enabled environment",
        "Non-Substitutable Evidence",
        "Initial-draft delivery is not a substitute for final journal submission readiness",
    ]:
        add(
            checks,
            f"final submission handoff records: {required_handoff_item}",
            required_handoff_item in final_submission_handoff,
            "final_submission_handoff.md",
        )
    add(
        checks,
        "PDF compilation handoff records status",
        "PDF handoff status: BLOCKED_NO_RENDERED_PDF" in pdf_compilation_handoff
        or "PDF handoff status: READY_FOR_RENDERED_PDF_INSPECTION" in pdf_compilation_handoff,
        "pdf_compilation_handoff.md",
    )
    for required_pdf_item in [
        "Compile command in a TeX-enabled environment",
        "Expected PDF output",
        "Rendered page-count inspection",
        "Rendered line/page numbering inspection",
        "Rendered table and figure inspection",
        "Rendered bibliography inspection",
        "Final author signoff form: `rendered_pdf_author_signoff_form.md`",
        "Non-Substitutable Evidence",
    ]:
        add(
            checks,
            f"PDF compilation handoff records: {required_pdf_item}",
            required_pdf_item in pdf_compilation_handoff,
            "pdf_compilation_handoff.md",
        )
    add(
        checks,
        "PDF render audit records status",
        "PDF render audit status:" in pdf_render_audit,
        "pdf_render_audit.md",
    )
    for required_render_item in [
        "Audit-only command: `python scripts/create_vsi_pdf_render_audit.py`",
        "Compile-and-audit command: `python scripts/create_vsi_pdf_render_audit.py --compile`",
        "Makefile audit target: `make -C manuscript_vsi_biomedical_data pdf-render-audit`",
        "Makefile compile target: `make -C manuscript_vsi_biomedical_data pdf-render-compile`",
        "Page range target: 20-35 pages",
        "Manual rendered review status: REQUIRED_AFTER_COMPILE",
        "Rendered page count:",
        "Required TeX tool: latexmk",
        "Required TeX tool: pdflatex",
        "Required TeX tool: bibtex",
        "Required TeX tool: kpsewhich",
        "Alternative TeX tool: tectonic",
        "Accepted TeX backend:",
        "Final author signoff form: `rendered_pdf_author_signoff_form.md`",
        "Completion Rule",
    ]:
        add(
            checks,
            f"PDF render audit records: {required_render_item}",
            required_render_item in pdf_render_audit,
            "pdf_render_audit.md",
        )
    add(
        checks,
        "rendered PDF visual prescreen records status",
        "Prescreen status: AUTOMATED_RENDERED_PDF_PRESCREEN_PASS_WITH_RESIDUAL_SIGNOFF_REQUIRED" in rendered_pdf_visual_prescreen
        or "Prescreen status: AI_RENDERED_PDF_PRESCREEN_PASS_WITH_RESIDUAL_SIGNOFF_REQUIRED" in rendered_pdf_visual_prescreen,
        "rendered_pdf_visual_prescreen.md",
    )
    for required_prescreen_item in [
        "Prescreen method: AUTOMATED_PDFINFO_PDFTOTEXT_PDFTOPPM_SAMPLE_RENDER",
        "Rendered page count:",
        "Rendered page count source:",
        "Line-number visibility: PASS",
        "Page-number visibility: PASS",
        "Body layout: PASS",
        "Table readability: PASS",
        "Figure readability: PASS",
        "Bibliography rendering: PASS",
        "Unresolved citation/reference markers: none detected",
        "Residual author/institutional placeholders: PRESENT",
        "Residual ethics/funding placeholders: PRESENT",
        "Clinical overlay pixel signoff: STILL REQUIRED",
        "Final submitting-author rendered-PDF signoff: STILL REQUIRED",
        "Final author signoff form: `rendered_pdf_author_signoff_form.md`",
    ]:
        add(
            checks,
            f"rendered PDF visual prescreen records: {required_prescreen_item}",
            required_prescreen_item in rendered_pdf_visual_prescreen,
            "rendered_pdf_visual_prescreen.md",
        )
    add(
        checks,
        "rendered PDF author signoff form records status",
        "Signoff status: RENDERED_PDF_AUTHOR_SIGNOFF_REQUIRED" in rendered_pdf_author_signoff_form
        or "Signoff status: RENDERED_PDF_AUTHOR_SIGNOFF_COMPLETE" in rendered_pdf_author_signoff_form,
        "rendered_pdf_author_signoff_form.md",
    )
    for required_pdf_signoff_item in [
        "PDF signoff checklist rows: 11",
        "Blocking signoff rows:",
        "Allowed final decisions:",
        "APPROVED_NO_CHANGES",
        "APPROVED_AFTER_CORRECTION",
        "NEEDS_CORRECTION_OR_RECOMPILE",
        "BLOCKED_BY_METADATA_OR_OTHER_SIGNOFF",
        "Final rendered-PDF decision:",
        "Reviewer and review date:",
        "Opened final PDF checked:",
        "Corrections or recompilation notes:",
        "reports/vsi_rendered_pdf_author_signoff_20260601.csv",
        "pdf_render_audit.md",
        "rendered_pdf_visual_prescreen.md",
        "clinical_overlay_signoff_form.md",
        "Completion Rule",
    ]:
        add(
            checks,
            f"rendered PDF author signoff form records: {required_pdf_signoff_item}",
            required_pdf_signoff_item in rendered_pdf_author_signoff_form,
            "rendered_pdf_author_signoff_form.md",
        )
    add(
        checks,
        "submission metadata preflight records status",
        "Status:" in metadata_preflight and "Blocking metadata checks:" in metadata_preflight,
        "submission_metadata_preflight.md",
    )
    for required_preflight_item in [
        "Article type is VSI: PR_Biomedical Data",
        "First author email finalized",
        "Ethics approval body finalized",
        "Funding statement finalized",
        "CRediT role finalized: conceptualization",
        "main.tex has no submission placeholders",
        "cover letter has finalized corresponding author details",
    ]:
        add(
            checks,
            f"submission metadata preflight records: {required_preflight_item}",
            required_preflight_item in metadata_preflight,
            "submission_metadata_preflight.md",
        )
    add(
        checks,
        "submission metadata preflight includes final verification command",
        "make -C manuscript_vsi_biomedical_data release" in metadata_preflight,
        "submission_metadata_preflight.md",
    )
    add(
        checks,
        "submission metadata lock audit records status",
        "Status: NOT_READY_FOR_METADATA_LOCK" in metadata_lock_audit or "Status: READY_FOR_METADATA_LOCK" in metadata_lock_audit,
        "submission_metadata_lock_audit.md",
    )
    for required_lock_item in [
        "Metadata field blockers:",
        "Preflight blocker count:",
        "main.tex placeholder hit count:",
        "cover_letter.txt placeholder hit count:",
        "Metadata template SHA256 prefix:",
        "Finalization Workflow",
        "make -C manuscript_vsi_biomedical_data release",
    ]:
        add(
            checks,
            f"submission metadata lock audit records: {required_lock_item}",
            required_lock_item in metadata_lock_audit,
            "submission_metadata_lock_audit.md",
        )
    add(
        checks,
        "submission blocker audit records outstanding count",
        "Outstanding blocker count:" in blocker_audit and "Status: NOT_SUBMISSION_READY" in blocker_audit,
        "submission_blocker_audit.md",
    )
    for blocker_id in [
        "BLOCKER_AUTHOR_METADATA",
        "BLOCKER_ETHICS_CONSENT",
        "BLOCKER_FUNDING_ACKNOWLEDGEMENTS",
        "BLOCKER_CREDIT_AUTHORSHIP",
        "BLOCKER_FINAL_TEX_PDF",
        "WARNING_REFERENCE_METADATA_REVIEW",
        "WARNING_CLINICAL_OVERLAY_PIXEL_REVIEW",
        "WARNING_OFFICIAL_REQUIREMENTS_RECHECK",
    ]:
        add(
            checks,
            f"submission blocker audit records: {blocker_id}",
            blocker_id in blocker_audit,
            "submission_blocker_audit.md",
        )
    add(
        checks,
        "submission blocker audit includes final verification command",
        "make -C manuscript_vsi_biomedical_data release" in blocker_audit,
        "submission_blocker_audit.md",
    )
    add(
        checks,
        "submission blocker audit includes author declaration signoff evidence",
        "author_declaration_signoff_form.md" in blocker_audit,
        "submission_blocker_audit.md",
    )
    quickstart = (root / "human_completion_quickstart.md").read_text() if (root / "human_completion_quickstart.md").exists() else ""
    for marker in [
        "Human Completion Quickstart",
        "Minimal Completion Sequence",
        "submission_metadata_author_fill_form.md",
        "author_declaration_signoff_form.md",
        "rendered_pdf_author_signoff_form.md",
        "reference_publisher_signoff_form.md",
        "clinical_overlay_signoff_form.md",
        "make -C manuscript_vsi_biomedical_data release",
    ]:
        add(
            checks,
            f"human completion quickstart records: {marker}",
            marker in quickstart,
            "human_completion_quickstart.md",
        )
    metadata_pipeline_dryrun = (root / "metadata_pipeline_dry_run_audit.md").read_text() if (root / "metadata_pipeline_dry_run_audit.md").exists() else ""
    for marker in [
        "Status: PASS",
        "Synthetic metadata passes application validation",
        "Planned manuscript updates are placeholder-free",
        "Synthetic metadata passes metadata preflight",
        "Blank optional ORCID remains acceptable",
    ]:
        add(
            checks,
            f"metadata pipeline dry-run records: {marker}",
            marker in metadata_pipeline_dryrun,
            "metadata_pipeline_dry_run_audit.md",
        )
    for marker in [
        "Package consistency status: PASS",
        "Current rendered PDF page count:",
        "Current highlight count:",
        "Stale 4-highlight claims absent",
        "Stale 21-page rendered PDF claims absent",
        "Article type consistent across metadata, cover letter, and upload index",
    ]:
        add(
            checks,
            f"package consistency audit records: {marker}",
            marker in package_consistency_audit,
            "package_consistency_audit.md",
        )
    add(
        checks,
        "clinical threshold audit report exists",
        bool(clinical_threshold_audit),
        clinical_threshold_audit_path,
    )
    for required_clinical_item in [
        "Dice >= 0.85",
        "29/31 (93.5%)",
        "Combined review gate",
        "25/31 (80.6%)",
        "not claimed as institutionally validated clinical acceptance criteria",
    ]:
        add(
            checks,
            f"clinical threshold audit records: {required_clinical_item}",
            required_clinical_item in clinical_threshold_audit,
            clinical_threshold_audit_path,
        )
    add(
        checks,
        "patient-aggregated paired comparison report exists",
        bool(patient_paired_report),
        patient_paired_report_path,
    )
    for required_patient_paired_item in [
        "Patient-mean rows: 21",
        "Repeated patients collapsed before testing: 8",
        "21/0",
        "0.569",
        "0.675",
        "0.776",
        "0.507",
        "does not create a patient-external validation claim",
    ]:
        add(
            checks,
            f"patient-aggregated paired report records: {required_patient_paired_item}",
            required_patient_paired_item in patient_paired_report,
            patient_paired_report_path,
        )
    for required_patient_paired_table_item in [
        r"\label{tab:patient-aggregated-paired-comparison}",
        "Patient-aggregated paired comparison",
        "0.569",
        "0.675",
        "0.776",
        "0.507",
        "21/0",
    ]:
        add(
            checks,
            f"patient-aggregated paired table records: {required_patient_paired_table_item}",
            required_patient_paired_table_item in patient_paired_table,
            "tables/patient_aggregated_paired_comparison.tex",
        )
    add(
        checks,
        "source evidence manifest records patient-aggregated paired comparison",
        "Patient-Aggregated Paired Comparison" in source_evidence_manifest
        and "tables/patient_aggregated_paired_comparison.tex" in source_evidence_manifest
        and "vsi_patient_aggregated_paired_comparison_20260601.csv" in source_evidence_manifest,
        "source_evidence_manifest.md",
    )
    add(
        checks,
        "traceability audit records patient-aggregated paired comparison",
        "Patient-mean paired comparison supports repeated-scan robustness" in traceability
        and "reports/vsi_patient_aggregated_paired_comparison_20260601.md" in traceability,
        "submission_requirements_traceability.md",
    )
    add(
        checks,
        "patient-aggregated robustness report exists",
        bool(patient_robustness_report),
        patient_robustness_report_path,
    )
    for required_patient_item in [
        "Unique patients after aggregation: 21",
        "Patients with repeated longitudinal scans: 8",
        "Patient-mean Dice",
        "Delta vs best baseline Dice",
        "<=0: 0/21",
        "does not create a patient-external validation claim",
    ]:
        add(
            checks,
            f"patient-aggregated robustness report records: {required_patient_item}",
            required_patient_item in patient_robustness_report,
            patient_robustness_report_path,
        )
    for required_patient_table_item in [
        r"\label{tab:patient-aggregated-robustness}",
        "Patient-aggregated robustness audit",
        "0.909",
        "0.861",
        "0/21",
        "repeated scans",
    ]:
        add(
            checks,
            f"patient-aggregated robustness table records: {required_patient_table_item}",
            required_patient_table_item in patient_robustness_table,
            "tables/patient_aggregated_robustness.tex",
        )
    add(
        checks,
        "source evidence manifest records patient-aggregated robustness",
        "Patient-Aggregated Robustness Analysis" in source_evidence_manifest
        and "tables/patient_aggregated_robustness.tex" in source_evidence_manifest
        and "vsi_patient_aggregated_robustness_20260601.csv" in source_evidence_manifest,
        "source_evidence_manifest.md",
    )
    add(
        checks,
        "traceability audit records patient-aggregated robustness",
        "Patient-aggregated robustness is reported" in traceability
        and "reports/vsi_patient_aggregated_robustness_20260601.md" in traceability,
        "submission_requirements_traceability.md",
    )
    add(
        checks,
        "prompt efficiency frontier report exists",
        bool(prompt_efficiency_report),
        prompt_efficiency_report_path,
    )
    for required_prompt_efficiency_item in [
        "VSI Prompt-Efficiency Frontier",
        "mild-expanded profile",
        "Dice gain per added prompt",
        "K=3 to K=7 gain recovered",
        "Oracle-gap reduction from K=3",
        "Interpretation:",
    ]:
        add(
            checks,
            f"prompt efficiency frontier report records: {required_prompt_efficiency_item}",
            required_prompt_efficiency_item in prompt_efficiency_report,
            prompt_efficiency_report_path,
        )
    for required_prompt_efficiency_table_item in [
        r"\label{tab:prompt-efficiency-frontier}",
        "Prompt-efficiency frontier",
        "Gain / added slice",
        "Recovered gain",
        "0.082",
        "0.022",
        "79.2",
    ]:
        add(
            checks,
            f"prompt efficiency frontier table records: {required_prompt_efficiency_table_item}",
            required_prompt_efficiency_table_item in prompt_efficiency_table,
            "tables/prompt_efficiency_frontier.tex",
        )
    add(
        checks,
        "source evidence manifest records prompt-efficiency frontier",
        "Prompt-Efficiency Frontier" in source_evidence_manifest
        and "tables/prompt_efficiency_frontier.tex" in source_evidence_manifest
        and "vsi_prompt_efficiency_frontier_20260531.csv" in source_evidence_manifest,
        "source_evidence_manifest.md",
    )
    add(
        checks,
        "traceability audit records prompt-efficiency frontier",
        "Prompt-efficiency frontier is reported" in traceability
        and "Prompt-efficiency claims trace to current ablation results" in traceability,
        "submission_requirements_traceability.md",
    )

    pngs = sorted((root / "figures").glob("*.png")) if (root / "figures").exists() else []
    for png in pngs:
        dims = png_dimensions(png)
        if not dims:
            add(checks, f"PNG readable: {png.name}", False, "not a readable PNG")
            continue
        width, height = dims
        add(checks, f"figure width >= 1772 px: {png.name}", width >= 1772, f"{width}x{height}")
        if png.name == "graphical_abstract.png":
            add(checks, "graphical abstract >= 1328x531 px", width >= 1328 and height >= 531, f"{width}x{height}")

    placeholder_hits = []
    for rel in ["main.tex", "cover_letter.txt", "README.md", "submission_checklist.md", "submission_metadata_template.yaml"]:
        text = (root / rel).read_text() if (root / rel).exists() else ""
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in text:
                placeholder_hits.append(f"{rel}: {pattern}")
    if placeholder_hits:
        blockers.extend(placeholder_hits)

    backend, backend_path = accepted_tex_backend()
    for tool in ["pdflatex", "latexmk", "kpsewhich"]:
        found = check_tool(tool)
        if found:
            add(checks, f"tool available: {tool}", True, found)
        elif backend == "tectonic":
            add(checks, f"tool available via accepted fallback instead of {tool}", True, f"tectonic: {backend_path}")
        else:
            warnings.append(f"TeX tool not available: {tool}")
    if backend != "none":
        add(checks, f"accepted TeX backend: {backend}", True, backend_path)
    else:
        warnings.append("No accepted TeX backend available: latexmk/pdflatex or Tectonic")

    local_cas_cls = root / "cas-sc.cls"
    cas_cls = kpsewhich_file("cas-sc.cls")
    if local_cas_cls.exists():
        add(checks, "Elsevier cas-sc.cls available", True, local_cas_cls)
    elif cas_cls:
        add(checks, "Elsevier cas-sc.cls available", True, cas_cls)
    else:
        warnings.append("Elsevier cas-sc.cls could not be located in this environment")

    all_checks_ok = all(row["ok"] for row in checks)
    return {
        "checks": checks,
        "warnings": warnings,
        "blockers": blockers,
        "all_checks_ok": all_checks_ok,
        "ready_for_submission": all_checks_ok and not blockers and not warnings,
    }


def render_markdown(result, root):
    status = "READY" if result["ready_for_submission"] else "NOT READY"
    lines = [
        "# VSI Manuscript Package Verification",
        "",
        f"Package: `{root}`",
        f"Status: **{status}**",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for row in result["checks"]:
        status_cell = "PASS" if row["ok"] else "FAIL"
        detail = row["detail"].replace("|", "\\|")
        lines.append(f"| {row['name']} | {status_cell} | {detail} |")

    lines.extend(["", "## Warnings", ""])
    if result["warnings"]:
        lines.extend(f"- {item}" for item in result["warnings"])
    else:
        lines.append("- None")

    lines.extend(["", "## Submission Blockers", ""])
    if result["blockers"]:
        lines.extend(f"- {item}" for item in result["blockers"])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A package can pass many source-structure checks while still being not ready for real submission if TeX tooling, official author metadata, IRB language, reference depth, figure resolution, final reference verification, or dated official-page evidence is missing.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Verify VSI manuscript package structure and blockers.")
    parser.add_argument("--root", default="manuscript_vsi_biomedical_data")
    parser.add_argument("--output", default="reports/vsi_manuscript_package_verification.md")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if the package is not submission-ready.")
    args = parser.parse_args()

    result = verify(args.root)
    report = render_markdown(result, args.root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(report)
    if args.strict and not result["ready_for_submission"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
