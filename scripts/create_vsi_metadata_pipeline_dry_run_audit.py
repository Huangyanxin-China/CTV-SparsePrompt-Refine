#!/usr/bin/env python3
"""Dry-run the approved-metadata propagation path with synthetic values.

This audit does not modify submission files and does not invent real author or
institutional metadata. It verifies that once approved values are supplied, the
local sync/preflight/apply code path can produce placeholder-free manuscript
updates, including the intended optional blank ORCID behavior.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "metadata_pipeline_dry_run_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_metadata_pipeline_dry_run_audit_20260601.csv"

sys.path.insert(0, str(ROOT / "scripts"))
import apply_vsi_submission_metadata as apply_meta  # noqa: E402
import create_vsi_submission_metadata_preflight as preflight  # noqa: E402


@dataclass(frozen=True)
class AuditRow:
    check: str
    status: str
    evidence: str
    interpretation: str


def synthetic_metadata() -> dict[str, Any]:
    return {
        "target_journal": "Pattern Recognition",
        "special_issue": "Multimodal Pattern Recognition for Biomedical Data: Theories, Algorithms, and Applications",
        "article_type": "VSI: PR_Biomedical Data",
        "submission_deadline": "2026-08-31",
        "manuscript": {
            "title": "Sparse-Prompted Multimodal CTV Completion with SDF Core-Envelope Priors for Lung Proton Therapy",
        },
        "authors": [
            {
                "name": "Yanxin Huang",
                "role": "first_author",
                "email": "yanxin.huang@example.edu",
                "affiliation_id": 1,
                "orcid": "",
            }
        ],
        "affiliations": [
            {
                "id": 1,
                "organization": "Example Institution for Dry Run",
                "city": "Example City",
                "country": "Example Country",
            }
        ],
        "corresponding_author": {
            "name": "Yanxin Huang",
            "email": "yanxin.huang@example.edu",
            "address": "Example Department, Example Institution, Example City, Example Country",
        },
        "ethics": {
            "approval_body": "Example Institutional Review Board",
            "approval_number": "Example approval or exemption ID",
            "consent_or_waiver": "Example consent waiver language for retrospective de-identified data.",
            "deidentification_statement": "Retrospective de-identified radiotherapy planning data.",
        },
        "funding": {
            "statement": "Example funding statement to be replaced by approved real text before submission.",
            "grant_numbers": [],
        },
        "author_contributions": {
            "conceptualization": "Yanxin Huang",
            "methodology": "Yanxin Huang",
            "software": "Yanxin Huang",
            "validation": "Yanxin Huang",
            "investigation": "Yanxin Huang",
            "writing_original_draft": "Yanxin Huang",
            "writing_review_editing": "Yanxin Huang",
            "supervision": "Yanxin Huang",
        },
    }


def yaml_text(data: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore
    except ImportError:
        return repr(data)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False, width=1000)


def placeholder_hits(text: str) -> list[str]:
    return [marker for marker in apply_meta.PLACEHOLDER_MARKERS if marker in text]


def build_rows() -> list[AuditRow]:
    data = synthetic_metadata()
    raw = yaml_text(data)
    rows: list[AuditRow] = []

    apply_rows = apply_meta.validate_metadata(data, raw, "")
    apply_blockers = [row for row in apply_rows if row.status == "BLOCKER"]
    rows.append(
        AuditRow(
            "Synthetic metadata passes application validation",
            "PASS" if not apply_blockers else "FAIL",
            f"{len(apply_blockers)} blocker(s)",
            "Approved metadata should be accepted by apply_vsi_submission_metadata.py before file writes.",
        )
    )

    try:
        updates = apply_meta.planned_updates(data)
        rows.append(
            AuditRow(
                "Synthetic metadata renders planned manuscript updates",
                "PASS",
                ", ".join(f"{name}: {len(content.splitlines())} lines" for name, content in updates.items()),
                "The current main.tex, cover letter, and CRediT replacement anchors are compatible with the apply script.",
            )
        )
    except Exception as exc:  # pragma: no cover - reports local template drift
        updates = {}
        rows.append(
            AuditRow(
                "Synthetic metadata renders planned manuscript updates",
                "FAIL",
                str(exc),
                "The apply script would need anchor or replacement repair before approved metadata can be propagated.",
            )
        )

    output_hits = sorted({hit for content in updates.values() for hit in placeholder_hits(content)})
    rows.append(
        AuditRow(
            "Planned manuscript updates are placeholder-free",
            "PASS" if not output_hits else "FAIL",
            ", ".join(output_hits) if output_hits else "no placeholder markers in planned outputs",
            "Synthetic approved metadata should remove the current submission placeholders from generated manuscript-facing files.",
        )
    )

    preflight_checks = [
        check
        for check in preflight.build_checks(data, raw)
        if check.name
        not in {
            "main.tex has no submission placeholders",
            "cover letter has finalized corresponding author details",
        }
    ]
    preflight_blockers = [check for check in preflight_checks if check.status == "BLOCKER"]
    rows.append(
        AuditRow(
            "Synthetic metadata passes metadata preflight",
            "PASS" if not preflight_blockers else "FAIL",
            f"{len(preflight_blockers)} blocker(s)",
            "The preflight should not block once required fields are finalized.",
        )
    )

    orcid_check = next((check for check in preflight_checks if check.name == "First author ORCID blank or valid"), None)
    rows.append(
        AuditRow(
            "Blank optional ORCID remains acceptable",
            "PASS" if orcid_check and orcid_check.status == "PASS" else "FAIL",
            orcid_check.evidence if orcid_check else "ORCID check not found",
            "The author may leave ORCID blank when no ORCID is provided; TODO placeholders must still be removed.",
        )
    )

    return rows


def write_csv(rows: list[AuditRow]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "evidence", "interpretation"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def write_markdown(rows: list[AuditRow]) -> None:
    fail_count = sum(1 for row in rows if row.status == "FAIL")
    status = "PASS" if fail_count == 0 else "FAIL"
    lines = [
        "# Metadata Pipeline Dry-Run Audit",
        "",
        "This non-destructive audit uses synthetic example values to verify the post-approval metadata propagation path. It does not modify submission files and does not supply real author, ethics, funding, or institutional information.",
        "",
        "## Summary",
        "",
        f"- Status: {status}",
        f"- Failing checks: {fail_count}",
        "- Synthetic ORCID policy: blank optional ORCID is valid after the placeholder is removed.",
        "- Real metadata source remains: `submission_metadata_author_fill_form.md` and `submission_metadata_template.yaml`.",
        "",
        "## Checks",
        "",
        "| Check | Status | Evidence | Interpretation |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        cells = [row.check, row.status, row.evidence, row.interpretation]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    lines.extend(
        [
            "",
            "## Completion Rule",
            "",
            "- This audit only proves the local scripts can accept a complete approved metadata object.",
            "- It is not author approval and must not be used as real metadata evidence.",
            "- After real values are approved, run the fill-form sync and metadata apply commands recorded in `human_completion_quickstart.md`.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    fail_count = sum(1 for row in rows if row.status == "FAIL")
    print(f"Wrote {MD_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Metadata pipeline dry-run status: {'PASS' if fail_count == 0 else 'FAIL'}; failing={fail_count}")


if __name__ == "__main__":
    main()
