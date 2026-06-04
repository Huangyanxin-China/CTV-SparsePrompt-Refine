#!/usr/bin/env python3
"""Create the initial-draft delivery handoff and package-local draft copy."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
SOURCE_DRAFT = ROOT / "reports" / "current_experiment_paper_draft_20260601.md"
PACKAGE_DRAFT = PKG / "current_experiment_paper_draft_20260601.md"
HANDOFF = PKG / "initial_draft_delivery_handoff.md"


def write_handoff() -> None:
    lines = [
        "# Initial Draft Delivery Handoff",
        "",
        "This handoff records the current deliverable requested by the user: an initial manuscript draft based on the current experiments, with institution-specific submission fields intentionally left for later human completion.",
        "",
        "## Delivery Status",
        "",
        "- Draft delivery status: INITIAL_DRAFT_DELIVERED",
        "- Delivery date: 2026-06-01 Asia/Shanghai",
        "- Scope: current-experiment manuscript draft and local TeX/PDF project",
        "- Not claimed: final journal submission readiness",
        "",
        "## Delivered Draft Files",
        "",
        "| Deliverable | Path | Status | Notes |",
        "| --- | --- | --- | --- |",
        "| Markdown initial draft | `manuscript_vsi_biomedical_data/current_experiment_paper_draft_20260601.md` | DELIVERED | Narrative draft based on current experiment results; mirrored from `reports/current_experiment_paper_draft_20260601.md`. |",
        "| TeX manuscript source | `manuscript_vsi_biomedical_data/main.tex` | DELIVERED | Elsevier CAS draft with placeholders retained where human metadata is required. |",
        "| Rendered PDF artifact | `manuscript_vsi_biomedical_data/main.pdf` | DELIVERED | Current compiled artifact for reading and review; final author signoff remains separate. |",
        "| Manuscript project archive | `manuscript_vsi_biomedical_data_20260531.tar.gz` | DELIVERED | Dated local package archive audited by `reports/vsi_archive_integrity_audit_20260531.md`. |",
        "",
        "## Current Paper Idea",
        "",
        "The delivered draft is centered on sparse-prompted multimodal CTV completion with SDF core-envelope priors. The supported claim is that CT, organ-at-risk masks, and a small number of clinician CTV slice prompts can be converted into strong 3D CTV completions by deterministic SDF propagation and core-envelope analysis.",
        "",
        "The current draft should not claim fully automatic CT-to-CTV segmentation. The doctor-prior graph refinement result is retained as a diagnostic negative/pilot result and future-work direction, not as the validated method.",
        "",
        "## Human-Fill Items for Later Submission",
        "",
        "| Area | Required human input | Local checklist |",
        "| --- | --- | --- |",
        "| Authors and affiliations | Final author list, order, institution names, city, country, corresponding author email, and address. | `submission_metadata_completion_packet.md` |",
        "| Ethics and consent | IRB or ethics committee name, approval or exemption number, and approved consent/waiver wording. | `submission_metadata_completion_packet.md` |",
        "| Funding and acknowledgements | Grant numbers, funder role, acknowledgements, or explicit no-specific-funding statement. | `submission_metadata_completion_packet.md` |",
        "| CRediT roles | Author-approved role assignments for all contribution categories. | `credit_author_statement.txt`; `submission_metadata_template.yaml` |",
        "| Final PDF signoff | Human inspection of the final PDF after metadata edits. | `pdf_compilation_handoff.md`; `rendered_pdf_visual_prescreen.md`; `rendered_pdf_author_signoff_form.md` |",
        "| Clinical overlay signoff | Full-resolution review of clinical overlay figures and rendered PDF panels. | `clinical_overlay_visual_review_packet.md`; `clinical_overlay_ai_visual_prescreen.md` |",
        "| Reference signoff | Final publisher-record check for every bibliography entry before upload. | `reference_publisher_verification_packet.md`; `reference_online_metadata_audit.md` |",
        "",
        "## Suggested Human Continuation Workflow",
        "",
        "1. Fill `submission_metadata_template.yaml` using `submission_metadata_completion_packet.md`.",
        "2. Run `python scripts/apply_vsi_submission_metadata.py --apply` after author approval.",
        "3. Recompile and inspect the final PDF.",
        "4. Complete reference and clinical overlay signoff.",
        "5. Run `make -C manuscript_vsi_biomedical_data release`.",
        "6. Require `reports/vsi_manuscript_package_verification.md` to report `Status: **READY**` before real journal upload.",
        "",
        "## Completion Boundary",
        "",
        "This file closes the requested initial-draft delivery. It does not close the full real-submission objective, because final author metadata, ethics/funding text, CRediT approval, final PDF inspection, reference signoff, and clinical overlay signoff require human or institutional approval.",
        "",
    ]
    HANDOFF.write_text("\n".join(lines))


def main() -> None:
    if not SOURCE_DRAFT.exists():
        raise SystemExit(f"Missing source draft: {SOURCE_DRAFT}")
    PKG.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_DRAFT, PACKAGE_DRAFT)
    write_handoff()
    print(f"Wrote {PACKAGE_DRAFT}")
    print(f"Wrote {HANDOFF}")


if __name__ == "__main__":
    main()
