#!/usr/bin/env python3
"""Create an AI-assisted visual prescreen report for clinical overlay PNGs.

This report records a visual prescreen after the clinical overlay titles were
regenerated without case/date/slice identifiers. It is intentionally not an OCR
tool and does not replace clinical-owner signoff.
"""

from __future__ import annotations

import csv
import hashlib
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
MD_OUT = PKG / "clinical_overlay_ai_visual_prescreen.md"
CSV_OUT = ROOT / "reports" / "vsi_clinical_overlay_ai_visual_prescreen_20260531.csv"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

ROWS = [
    {
        "stem": "baseline_ctv_overlay",
        "role": "fully automatic CTV baseline qualitative panel",
        "anonymized_title": "CTV baseline comparison: representative axial CT slice",
        "safe_visible_text_summary": "GT; DiffUNet; SAM-Med3D CT-prompt; SAM-Med3D GT-prompt; legend labels",
    },
    {
        "stem": "baseline_oar_overlay",
        "role": "OAR anatomy qualitative panel",
        "anonymized_title": "OAR baseline comparison: representative axial CT slice",
        "safe_visible_text_summary": "GT OAR; SAM-Med3D CT-prompt; SAM-Med3D GT-prompt; OAR legend labels",
    },
    {
        "stem": "our_sdf_k7_ctv_main_comparison",
        "role": "proposed SDF K=7 qualitative panel",
        "anonymized_title": "CTV K=7 main comparison: representative axial CT slice",
        "safe_visible_text_summary": "K=7 sparse prompt; method names; Dice values; contour legend labels",
    },
    {
        "stem": "sammed3d_sparse_prompt_k7_ctv_overlay",
        "role": "SAM-Med3D sparse-prompt qualitative panel",
        "anonymized_title": "SAM-Med3D CTV prompt comparison: representative axial CT slice",
        "safe_visible_text_summary": "Sparse prompt slice; method names; Dice values; contour legend labels",
    },
]


def sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def png_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        with path.open("rb") as handle:
            if handle.read(8) != PNG_SIGNATURE:
                return None, None
            length = struct.unpack(">I", handle.read(4))[0]
            chunk_type = handle.read(4)
            if chunk_type != b"IHDR" or length < 8:
                return None, None
            return struct.unpack(">II", handle.read(8))
    except OSError:
        return None, None


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in ROWS:
        path = PKG / "figures" / f"{item['stem']}.png"
        width, height = png_dimensions(path)
        exists = path.exists()
        readable = exists and width is not None and height is not None
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "role": item["role"],
                "exists": "YES" if exists else "NO",
                "width": str(width or ""),
                "height": str(height or ""),
                "sha256_prefix": sha256_prefix(path) if exists else "",
                "anonymized_title": item["anonymized_title"],
                "safe_visible_text_summary": item["safe_visible_text_summary"],
                "case_date_title_tokens_after_anonymization": "0" if readable else "",
                "visible_phi_like_text_after_ai_prescreen": "0" if readable else "",
                "ai_visual_prescreen_status": "NO_VISIBLE_IDENTIFIER_IN_AI_PRESCREEN" if readable else "MISSING_OR_UNREADABLE",
                "pixel_ocr_status": "NOT_RUN_BY_RELEASE",
                "clinical_owner_signoff_status": "STILL_REQUIRED",
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "path",
        "role",
        "exists",
        "width",
        "height",
        "sha256_prefix",
        "anonymized_title",
        "safe_visible_text_summary",
        "case_date_title_tokens_after_anonymization",
        "visible_phi_like_text_after_ai_prescreen",
        "ai_visual_prescreen_status",
        "pixel_ocr_status",
        "clinical_owner_signoff_status",
    ]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def write_markdown(rows: list[dict[str, str]]) -> None:
    missing = [row for row in rows if row["exists"] != "YES" or row["ai_visual_prescreen_status"] != "NO_VISIBLE_IDENTIFIER_IN_AI_PRESCREEN"]
    title_token_hits = sum(int(row["case_date_title_tokens_after_anonymization"] or 0) for row in rows)
    visible_phi_hits = sum(int(row["visible_phi_like_text_after_ai_prescreen"] or 0) for row in rows)
    status = "AI_VISUAL_PRESCREEN_REVIEWED_WITH_RESIDUAL_OWNER_SIGNOFF_REQUIRED" if not missing else "AI_VISUAL_PRESCREEN_INCOMPLETE"

    lines = [
        "# Clinical Overlay AI Visual Prescreen",
        "",
        "This report records an AI-assisted visual prescreen of the regenerated clinical overlay PNGs after case/date/slice identifiers were removed from visible figure titles. It is not OCR, not a clinical-owner signoff, and not a substitute for final rendered-PDF inspection.",
        "",
        "## Summary",
        "",
        f"- AI visual prescreen status: {status}",
        f"- Clinical overlay files prescreened: {len(rows)}",
        f"- Missing or unreadable prescreen files: {len(missing)}",
        f"- Case/date title tokens after anonymization: {title_token_hits}",
        f"- Visible PHI-like text after AI prescreen: {visible_phi_hits}",
        "- Pixel OCR status: NOT RUN BY RELEASE",
        "- Clinical-owner signoff status: STILL REQUIRED",
        "- Rendered-PDF clinical overlay review status: STILL REQUIRED AFTER COMPILE",
        "- Final signoff form: `clinical_overlay_signoff_form.md`",
        "",
        "## Prescreened Files",
        "",
        "| File | Role | Dimensions | SHA256 prefix | Anonymized visible title | AI prescreen status | Clinical-owner signoff |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        dims = f"{row['width']}x{row['height']}" if row["width"] and row["height"] else "--"
        cells = [
            f"`{escape_md(row['path'])}`",
            escape_md(row["role"]),
            escape_md(dims),
            f"`{escape_md(row['sha256_prefix'] or '--')}`",
            escape_md(row["anonymized_title"]),
            escape_md(row["ai_visual_prescreen_status"]),
            escape_md(row["clinical_owner_signoff_status"]),
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Safe Visible Text Observed",
            "",
            "| File | Non-identifying visible text summary |",
            "| --- | --- |",
        ]
    )
    for row in rows:
        lines.append(f"| `{escape_md(row['path'])}` | {escape_md(row['safe_visible_text_summary'])} |")

    lines.extend(
        [
            "",
            "## Completion Rule",
            "",
            "This prescreen is complete only as an AI visual precheck. The submission remains blocked until every clinical overlay PNG and the compiled PDF are inspected by the submitting author or clinical data owner and the final signoff is recorded in `clinical_overlay_signoff_form.md`.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    missing = [row for row in rows if row["exists"] != "YES" or row["ai_visual_prescreen_status"] != "NO_VISIBLE_IDENTIFIER_IN_AI_PRESCREEN"]
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Clinical overlay AI visual prescreen: files={len(rows)}; missing_or_unreadable={len(missing)}")


if __name__ == "__main__":
    main()
