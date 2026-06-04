#!/usr/bin/env python3
"""Create a reproducibility manifest for the VSI manuscript package."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "manuscript_vsi_biomedical_data" / "reproducibility_manifest.md"

OFFICIAL_SOURCES = [
    "https://www.sciencedirect.com/special-issue/329765/multimodal-pattern-recognition-for-biomedical-data-theories-algorithms-and-applications",
    "https://www.sciencedirect.com/journal/pattern-recognition/publish/guide-for-authors",
]

PRIMARY_INPUTS = [
    "reports/frontier_literature_and_project_idea_20260531.md",
    "reports/ctv_main_experiment_results.csv",
    "reports/ctv_main_per_case_comparison.csv",
    "reports/ctv_core_envelope_delta_summary.csv",
    "results/method_validation_ablation_suite/summary.csv",
    "results/method_validation_ablation_suite/per_case_metrics.csv",
    "nnunet_runs/Dataset015_CTV_Dataset004Split/preprocessed/Dataset015_CTV_Dataset004Split/splits_final.json",
    "nnunet_runs/Dataset014_ThoracicOAR_Dataset004Split/preprocessed/Dataset014_ThoracicOAR_Dataset004Split/splits_final.json",
    "results/doctor_prior_graph_refinement_minisplit5_cached/doctor_prior_split.json",
    "results/doctor_prior_graph_refinement_fast10_k3_cached/doctor_prior_split.json",
    "results/doctor_prior_graph_refinement_fast10_k3_cached/doctor_prior_summary.csv",
    "results/doctor_prior_graph_refinement_fast10_k3_cached/doctor_prior_thresholds.csv",
    "reports/doctor_prior_graph_refinement_fast10_k3_cached_summary.md",
]

GENERATION_SCRIPTS = [
    "scripts/create_vsi_manuscript_figures.py",
    "scripts/create_vsi_figure_privacy_integrity_audit.py",
    "scripts/create_vsi_clinical_overlay_visual_review_packet.py",
    "scripts/create_vsi_clinical_overlay_ai_visual_prescreen.py",
    "scripts/create_vsi_clinical_overlay_signoff_form.py",
    "scripts/create_vsi_paired_statistical_comparison.py",
    "scripts/create_vsi_patient_aggregated_paired_comparison.py",
    "scripts/create_vsi_case_level_robustness_analysis.py",
    "scripts/create_vsi_patient_aggregated_robustness_analysis.py",
    "scripts/create_vsi_clinical_threshold_failure_audit.py",
    "scripts/create_vsi_external_validity_public_data_audit.py",
    "scripts/create_vsi_validation_split_leakage_audit.py",
    "scripts/create_vsi_frontier_recommendation_traceability.py",
    "scripts/create_vsi_official_requirements_snapshot.py",
    "scripts/create_vsi_initial_draft_delivery_handoff.py",
    "scripts/create_vsi_objective_completion_audit.py",
    "scripts/apply_vsi_submission_metadata.py",
    "scripts/sync_vsi_submission_metadata_from_fill_form.py",
    "scripts/create_vsi_submission_metadata_completion_packet.py",
    "scripts/create_vsi_metadata_pipeline_dry_run_audit.py",
    "scripts/create_vsi_human_completion_quickstart.py",
    "scripts/create_vsi_final_submission_handoff.py",
    "scripts/create_vsi_package_consistency_audit.py",
    "scripts/create_vsi_pdf_compilation_handoff.py",
    "scripts/create_vsi_pdf_render_audit.py",
    "scripts/create_vsi_rendered_pdf_visual_prescreen.py",
    "scripts/create_vsi_rendered_pdf_author_signoff_form.py",
    "scripts/create_vsi_author_declaration_signoff_form.py",
    "scripts/create_vsi_prompt_strategy_robustness_analysis.py",
    "scripts/create_vsi_prompt_efficiency_analysis.py",
    "scripts/create_vsi_oar_constraint_sensitivity_analysis.py",
    "scripts/create_vsi_source_layout_audit.py",
    "scripts/create_vsi_tex_compile_readiness_audit.py",
    "scripts/create_vsi_submission_metadata_preflight.py",
    "scripts/create_vsi_submission_metadata_lock_audit.py",
    "scripts/create_vsi_submission_blocker_audit.py",
    "scripts/create_vsi_citation_metadata_audit.py",
    "scripts/create_vsi_reference_identifier_audit.py",
    "scripts/create_vsi_reference_publisher_verification_packet.py",
    "scripts/create_vsi_reference_online_metadata_audit.py",
    "scripts/create_vsi_reference_publisher_signoff_form.py",
    "scripts/create_vsi_archive_integrity_audit.py",
    "scripts/create_vsi_reproducibility_manifest.py",
    "scripts/verify_vsi_manuscript_package.py",
    "scripts/archive/historical_experiments/run_doctor_prior_graph_refinement.py",
    "scripts/archive/historical_experiments/run_method_validation_ablation_suite.py",
]

MANUSCRIPT_ARTIFACTS = [
    "manuscript_vsi_biomedical_data/main.tex",
    "manuscript_vsi_biomedical_data/current_experiment_paper_draft_20260601.md",
    "manuscript_vsi_biomedical_data/main.pdf",
    "manuscript_vsi_biomedical_data/Makefile",
    "manuscript_vsi_biomedical_data/references.bib",
    "manuscript_vsi_biomedical_data/highlights.tex",
    "manuscript_vsi_biomedical_data/cover_letter.txt",
    "manuscript_vsi_biomedical_data/data_availability_statement.txt",
    "manuscript_vsi_biomedical_data/declaration_of_interest.txt",
    "manuscript_vsi_biomedical_data/generative_ai_statement.txt",
    "manuscript_vsi_biomedical_data/credit_author_statement.txt",
    "manuscript_vsi_biomedical_data/submission_checklist.md",
    "manuscript_vsi_biomedical_data/submission_metadata_template.yaml",
    "manuscript_vsi_biomedical_data/submission_requirements_traceability.md",
    "manuscript_vsi_biomedical_data/official_requirements_snapshot.md",
    "manuscript_vsi_biomedical_data/reproducibility_manifest.md",
    "manuscript_vsi_biomedical_data/editorial_manager_upload_index.md",
    "manuscript_vsi_biomedical_data/citation_metadata_audit.md",
    "manuscript_vsi_biomedical_data/reference_identifier_audit.md",
    "manuscript_vsi_biomedical_data/reference_publisher_verification_packet.md",
    "manuscript_vsi_biomedical_data/reference_online_metadata_audit.md",
    "manuscript_vsi_biomedical_data/reference_publisher_signoff_form.md",
    "manuscript_vsi_biomedical_data/source_layout_audit.md",
    "manuscript_vsi_biomedical_data/tex_compile_readiness_audit.md",
    "manuscript_vsi_biomedical_data/external_validity_public_data_audit.md",
    "manuscript_vsi_biomedical_data/validation_split_leakage_audit.md",
    "manuscript_vsi_biomedical_data/frontier_recommendation_traceability.md",
    "manuscript_vsi_biomedical_data/objective_completion_audit.md",
    "manuscript_vsi_biomedical_data/initial_draft_delivery_handoff.md",
    "manuscript_vsi_biomedical_data/metadata_application_plan.md",
    "manuscript_vsi_biomedical_data/submission_metadata_completion_packet.md",
    "manuscript_vsi_biomedical_data/submission_metadata_author_fill_form.md",
    "manuscript_vsi_biomedical_data/submission_metadata_fill_form_sync.md",
    "manuscript_vsi_biomedical_data/metadata_pipeline_dry_run_audit.md",
    "manuscript_vsi_biomedical_data/package_consistency_audit.md",
    "manuscript_vsi_biomedical_data/human_completion_quickstart.md",
    "manuscript_vsi_biomedical_data/final_submission_handoff.md",
    "manuscript_vsi_biomedical_data/pdf_compilation_handoff.md",
    "manuscript_vsi_biomedical_data/pdf_render_audit.md",
    "manuscript_vsi_biomedical_data/rendered_pdf_visual_prescreen.md",
    "manuscript_vsi_biomedical_data/rendered_pdf_author_signoff_form.md",
    "manuscript_vsi_biomedical_data/author_declaration_signoff_form.md",
    "manuscript_vsi_biomedical_data/submission_metadata_preflight.md",
    "manuscript_vsi_biomedical_data/submission_metadata_lock_audit.md",
    "manuscript_vsi_biomedical_data/submission_blocker_audit.md",
    "manuscript_vsi_biomedical_data/author_submission_info_needed.md",
    "manuscript_vsi_biomedical_data/graphical_abstract_description.txt",
    "manuscript_vsi_biomedical_data/figure_privacy_integrity_audit.md",
    "manuscript_vsi_biomedical_data/clinical_overlay_visual_review_packet.md",
    "manuscript_vsi_biomedical_data/clinical_overlay_ai_visual_prescreen.md",
    "manuscript_vsi_biomedical_data/clinical_overlay_signoff_form.md",
    "manuscript_vsi_biomedical_data/README.md",
    "manuscript_vsi_biomedical_data/source_evidence_manifest.md",
    "manuscript_vsi_biomedical_data/peer_review_risk_audit.md",
    "manuscript_vsi_biomedical_data/tables/main_results.tex",
    "manuscript_vsi_biomedical_data/tables/paired_statistical_comparison.tex",
    "manuscript_vsi_biomedical_data/tables/patient_aggregated_paired_comparison.tex",
    "manuscript_vsi_biomedical_data/tables/case_level_robustness.tex",
    "manuscript_vsi_biomedical_data/tables/patient_aggregated_robustness.tex",
    "manuscript_vsi_biomedical_data/tables/clinical_threshold_failure_audit.tex",
    "manuscript_vsi_biomedical_data/tables/prompt_count_sensitivity.tex",
    "manuscript_vsi_biomedical_data/tables/prompt_efficiency_frontier.tex",
    "manuscript_vsi_biomedical_data/tables/prompt_strategy_robustness.tex",
    "manuscript_vsi_biomedical_data/tables/oar_constraint_sensitivity.tex",
    "manuscript_vsi_biomedical_data/tables/core_envelope_ablation.tex",
    "manuscript_vsi_biomedical_data/tables/oracle_headroom.tex",
    "manuscript_vsi_biomedical_data/tables/doctor_prior_minisplit.tex",
    "manuscript_vsi_biomedical_data/figures/vsi_method_workflow.png",
    "manuscript_vsi_biomedical_data/figures/vsi_main_results_dice.png",
    "manuscript_vsi_biomedical_data/figures/vsi_prompt_sensitivity_headroom.png",
    "manuscript_vsi_biomedical_data/figures/vsi_doctor_prior_diagnostic.png",
    "manuscript_vsi_biomedical_data/figures/baseline_ctv_overlay.png",
    "manuscript_vsi_biomedical_data/figures/baseline_oar_overlay.png",
    "manuscript_vsi_biomedical_data/figures/sammed3d_sparse_prompt_k7_ctv_overlay.png",
    "manuscript_vsi_biomedical_data/figures/our_sdf_k7_ctv_main_comparison.png",
    "manuscript_vsi_biomedical_data/figures/graphical_abstract.png",
    "manuscript_vsi_biomedical_data/figures/vsi_method_workflow.pdf",
    "manuscript_vsi_biomedical_data/figures/vsi_main_results_dice.pdf",
    "manuscript_vsi_biomedical_data/figures/vsi_prompt_sensitivity_headroom.pdf",
    "manuscript_vsi_biomedical_data/figures/vsi_doctor_prior_diagnostic.pdf",
    "manuscript_vsi_biomedical_data/figures/graphical_abstract.pdf",
]

DERIVED_REPORTS = [
    "reports/vsi_figure_privacy_integrity_audit_20260531.csv",
    "reports/vsi_clinical_overlay_visual_review_packet_20260531.csv",
    "reports/vsi_clinical_overlay_ai_visual_prescreen_20260531.csv",
    "reports/vsi_clinical_overlay_signoff_20260531.csv",
    "reports/vsi_main_paired_statistical_comparison_20260531.csv",
    "reports/vsi_main_paired_statistical_comparison_20260531.md",
    "reports/vsi_patient_aggregated_paired_comparison_20260601.csv",
    "reports/vsi_patient_aggregated_paired_comparison_20260601.md",
    "reports/vsi_case_level_robustness_20260531.csv",
    "reports/vsi_case_level_robustness_20260531.md",
    "reports/vsi_patient_aggregated_robustness_20260601.csv",
    "reports/vsi_patient_aggregated_robustness_20260601.md",
    "reports/vsi_clinical_threshold_failure_audit_20260531.csv",
    "reports/vsi_clinical_threshold_failure_audit_20260531.md",
    "reports/vsi_external_validity_public_data_audit_20260531.csv",
    "reports/vsi_validation_split_leakage_audit_20260601.csv",
    "reports/vsi_frontier_recommendation_traceability_20260531.csv",
    "reports/vsi_official_requirements_snapshot_20260531.csv",
    "reports/vsi_objective_completion_audit_20260531.csv",
    "reports/vsi_metadata_application_plan_20260531.csv",
    "reports/vsi_submission_metadata_completion_packet_20260531.csv",
    "reports/vsi_submission_metadata_fill_form_sync_20260531.csv",
    "reports/vsi_metadata_pipeline_dry_run_audit_20260601.csv",
    "reports/vsi_package_consistency_audit_20260601.csv",
    "reports/vsi_human_completion_quickstart_20260601.csv",
    "reports/vsi_final_submission_handoff_20260531.csv",
    "reports/vsi_pdf_compilation_handoff_20260531.csv",
    "reports/vsi_pdf_render_audit_20260531.csv",
    "reports/vsi_rendered_pdf_visual_prescreen_20260601.csv",
    "reports/vsi_rendered_pdf_author_signoff_20260601.csv",
    "reports/vsi_author_declaration_signoff_20260601.csv",
    "reports/vsi_prompt_efficiency_frontier_20260531.csv",
    "reports/vsi_prompt_efficiency_frontier_20260531.md",
    "reports/vsi_prompt_strategy_robustness_20260531.csv",
    "reports/vsi_prompt_strategy_robustness_20260531.md",
    "reports/vsi_oar_constraint_sensitivity_20260531.csv",
    "reports/vsi_oar_constraint_sensitivity_20260531.md",
    "reports/vsi_citation_metadata_audit_20260531.csv",
    "reports/vsi_reference_identifier_audit_20260531.csv",
    "reports/vsi_reference_publisher_verification_packet_20260531.csv",
    "reports/vsi_reference_online_metadata_audit_20260531.csv",
    "reports/vsi_reference_publisher_signoff_20260531.csv",
    "reports/vsi_tex_compile_readiness_audit_20260531.csv",
    "reports/vsi_submission_metadata_lock_audit_20260531.csv",
    "reports/vsi_manuscript_package_verification.md",
    "reports/vsi_paper_closure_status_20260531.md",
    "reports/current_experiment_paper_draft_20260601.md",
]

REGENERATION_COMMANDS = [
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
    "python scripts/create_vsi_metadata_pipeline_dry_run_audit.py",
    "python scripts/create_vsi_human_completion_quickstart.py",
    "python scripts/create_vsi_final_submission_handoff.py",
    "python scripts/create_vsi_package_consistency_audit.py",
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
    "python scripts/create_vsi_reference_online_metadata_audit.py --refresh",
    "python scripts/create_vsi_reproducibility_manifest.py",
    "python scripts/verify_vsi_manuscript_package.py",
    "python -m py_compile scripts/verify_vsi_manuscript_package.py scripts/create_vsi_manuscript_figures.py scripts/create_vsi_figure_privacy_integrity_audit.py scripts/create_vsi_clinical_overlay_visual_review_packet.py scripts/create_vsi_clinical_overlay_ai_visual_prescreen.py scripts/create_vsi_clinical_overlay_signoff_form.py scripts/create_vsi_rendered_pdf_author_signoff_form.py scripts/create_vsi_rendered_pdf_visual_prescreen.py scripts/create_vsi_author_declaration_signoff_form.py scripts/create_vsi_paired_statistical_comparison.py scripts/create_vsi_patient_aggregated_paired_comparison.py scripts/create_vsi_case_level_robustness_analysis.py scripts/create_vsi_patient_aggregated_robustness_analysis.py scripts/create_vsi_clinical_threshold_failure_audit.py scripts/create_vsi_external_validity_public_data_audit.py scripts/create_vsi_validation_split_leakage_audit.py scripts/create_vsi_frontier_recommendation_traceability.py scripts/create_vsi_official_requirements_snapshot.py scripts/create_vsi_initial_draft_delivery_handoff.py scripts/create_vsi_objective_completion_audit.py scripts/apply_vsi_submission_metadata.py scripts/sync_vsi_submission_metadata_from_fill_form.py scripts/create_vsi_submission_metadata_completion_packet.py scripts/create_vsi_final_submission_handoff.py scripts/create_vsi_package_consistency_audit.py scripts/create_vsi_pdf_compilation_handoff.py scripts/create_vsi_pdf_render_audit.py scripts/create_vsi_prompt_strategy_robustness_analysis.py scripts/create_vsi_prompt_efficiency_analysis.py scripts/create_vsi_oar_constraint_sensitivity_analysis.py scripts/create_vsi_source_layout_audit.py scripts/create_vsi_tex_compile_readiness_audit.py scripts/create_vsi_submission_metadata_preflight.py scripts/create_vsi_submission_metadata_lock_audit.py scripts/create_vsi_submission_blocker_audit.py scripts/create_vsi_citation_metadata_audit.py scripts/create_vsi_reference_identifier_audit.py scripts/create_vsi_reference_publisher_verification_packet.py scripts/create_vsi_reference_online_metadata_audit.py scripts/create_vsi_reference_publisher_signoff_form.py scripts/create_vsi_archive_integrity_audit.py scripts/create_vsi_reproducibility_manifest.py scripts/archive/historical_experiments/run_doctor_prior_graph_refinement.py",
    "make -C manuscript_vsi_biomedical_data archive",
    "python scripts/create_vsi_archive_integrity_audit.py",
]


def sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def file_row(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        return f"| `{rel}` | MISSING | -- | -- |"
    return f"| `{rel}` | present | {path.stat().st_size} | `{sha256_prefix(path)}` |"


def table_section(title: str, files: list[str]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Path | Status | Bytes | SHA256 prefix |",
        "| --- | --- | ---: | --- |",
    ]
    lines.extend(file_row(rel) for rel in files)
    lines.append("")
    return lines


def main() -> None:
    lines = [
        "# Reproducibility Manifest",
        "",
        "This manifest records the local inputs, scripts, generated tables, figures, and verification commands for the Pattern Recognition VSI manuscript package.",
        "",
        "## Official Sources",
        "",
    ]
    lines.extend(f"- {url}" for url in OFFICIAL_SOURCES)
    lines.extend(["", "## Regeneration Commands", ""])
    lines.extend(f"- `{cmd}`" for cmd in REGENERATION_COMMANDS)
    lines.append("")
    lines.extend(table_section("Primary Inputs", PRIMARY_INPUTS))
    lines.extend(table_section("Generation Scripts", GENERATION_SCRIPTS))
    lines.extend(table_section("Manuscript Artifacts", MANUSCRIPT_ARTIFACTS))
    lines.extend(table_section("Derived Reports", DERIVED_REPORTS))
    lines.extend(
        [
            "## Known Non-Reproducible Submission Items",
            "",
            "- Final author names, affiliations, and corresponding author contact details require author confirmation.",
            "- IRB or ethics approval language and funding information require institutional confirmation.",
            "- `author_declaration_signoff_form.md` records the required final row-level author, declaration, and responsible-authority approvals; blank rows remain submission blockers.",
            "- Local PDF compilation has been verified through the Tectonic fallback recorded in `pdf_render_audit.md`; this does not replace final human rendered-PDF inspection.",
            "- `pdf_render_audit.md` records the executable PDF compile/audit path, accepted TeX backend, PDF/log presence, page count, and current manual rendered-PDF review gate.",
            "- `rendered_pdf_visual_prescreen.md` records automated page rendering and text-extraction prescreen evidence for the current compiled PDF; it does not replace final human rendered-PDF inspection.",
            "- `rendered_pdf_author_signoff_form.md` records the required final submitting-author rendered-PDF decisions; blank rows remain submission blockers.",
            "- `clinical_overlay_ai_visual_prescreen.md` records an AI-assisted precheck after anonymized-title regeneration, but it does not replace clinical-owner signoff or rendered-PDF inspection.",
            "- `clinical_overlay_signoff_form.md` records the required final row-level human decisions for clinical overlay pixel review; blank rows remain submission blockers.",
            "- `reference_online_metadata_audit.md` uses a cached Crossref/arXiv/DataCite/PublisherURL snapshot during release; refresh it with `--refresh` immediately before final submission if reference metadata may have changed.",
            "- Private clinical imaging data cannot be redistributed from this package; aggregate metrics and scripts are used for manuscript verification.",
            "- Official ScienceDirect special-issue and Pattern Recognition guide requirements were rechecked for the current dated package; repeat the recheck if upload occurs after the recorded access date or if either official page changes.",
            "",
        ]
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
