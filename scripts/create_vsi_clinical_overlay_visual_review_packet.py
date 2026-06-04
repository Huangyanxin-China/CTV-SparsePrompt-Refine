#!/usr/bin/env python3
"""Create a clinical-overlay visual review packet for manuscript figures."""

from __future__ import annotations

import csv
import hashlib
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "manuscript_vsi_biomedical_data"
FIGURE_AUDIT_CSV = ROOT / "reports" / "vsi_figure_privacy_integrity_audit_20260531.csv"
MD_OUT = PKG / "clinical_overlay_visual_review_packet.md"
CSV_OUT = ROOT / "reports" / "vsi_clinical_overlay_visual_review_packet_20260531.csv"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ROLE_BY_STEM = {
    "baseline_ctv_overlay": "fully automatic CTV baseline qualitative panel",
    "baseline_oar_overlay": "OAR anatomy qualitative panel",
    "sammed3d_sparse_prompt_k7_ctv_overlay": "SAM-Med3D sparse-prompt qualitative panel",
    "our_sdf_k7_ctv_main_comparison": "proposed SDF K=7 qualitative panel",
}
PHI_CHECKS = [
    "patient name",
    "MRN or accession number",
    "DOB or full service date",
    "scanner/PACS viewport overlay",
    "institutional label embedded in image pixels",
    "free-text annotation that could identify a patient",
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


def read_figure_audit() -> list[dict[str, str]]:
    if not FIGURE_AUDIT_CSV.exists():
        return []
    with FIGURE_AUDIT_CSV.open(newline="") as handle:
        return list(csv.DictReader(handle))


def clinical_rows_from_audit() -> list[dict[str, str]]:
    rows = []
    for row in read_figure_audit():
        if row.get("clinical_pixel_review_required") == "YES":
            rows.append(row)
    return rows


def fallback_clinical_paths() -> list[Path]:
    return [PKG / "figures" / f"{stem}.png" for stem in ROLE_BY_STEM]


def packet_row(path: Path, audit_row: dict[str, str] | None = None) -> dict[str, str]:
    width, height = png_dimensions(path)
    stem = path.stem
    audit_row = audit_row or {}
    exists = path.exists()
    readable = "PASS" if exists and width and height else "MISSING_OR_UNREADABLE"
    filename_hits = audit_row.get("filename_phi_hits", "")
    metadata_hits = audit_row.get("metadata_phi_hits", "")
    metadata_status = "PASS" if not filename_hits and not metadata_hits else "REVIEW_METADATA_HIT"
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "role": ROLE_BY_STEM.get(stem, "clinical overlay qualitative panel"),
        "exists": "YES" if exists else "NO",
        "width": str(width or audit_row.get("width", "")),
        "height": str(height or audit_row.get("height", "")),
        "sha256_prefix": sha256_prefix(path) if exists else "",
        "filename_phi_hits": filename_hits,
        "metadata_phi_hits": metadata_hits,
        "readable_status": readable,
        "metadata_status": metadata_status,
        "pixel_ocr_status": "NOT_RUN_BY_RELEASE",
        "manual_visual_status": "REQUIRED",
        "clinical_owner_signoff_status": "REQUIRED",
        "required_checks": "; ".join(PHI_CHECKS),
    }


def build_rows() -> list[dict[str, str]]:
    audit_rows = clinical_rows_from_audit()
    if audit_rows:
        rows = []
        for audit_row in audit_rows:
            rows.append(packet_row(ROOT / audit_row["path"], audit_row))
        return rows
    return [packet_row(path) for path in fallback_clinical_paths()]


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "path",
        "role",
        "exists",
        "width",
        "height",
        "sha256_prefix",
        "filename_phi_hits",
        "metadata_phi_hits",
        "readable_status",
        "metadata_status",
        "pixel_ocr_status",
        "manual_visual_status",
        "clinical_owner_signoff_status",
        "required_checks",
    ]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def write_markdown(rows: list[dict[str, str]]) -> None:
    missing = [row for row in rows if row["exists"] != "YES" or row["readable_status"] != "PASS"]
    filename_hits = [row for row in rows if row["filename_phi_hits"]]
    metadata_hits = [row for row in rows if row["metadata_phi_hits"]]
    lines = [
        "# Clinical Overlay Visual Review Packet",
        "",
        "This packet is the author-facing queue for pixel-level visual PHI review of clinical overlay figures. It uses the figure privacy/integrity audit as input and keeps final clinical-owner signoff explicit. It does not perform OCR and does not replace human inspection of image pixels.",
        "",
        "## Summary",
        "",
        "- Packet status: CLINICAL_OVERLAY_VISUAL_REVIEW_REQUIRED",
        f"- Clinical overlay files queued: {len(rows)}",
        f"- Missing or unreadable queued files: {len(missing)}",
        f"- Filename PHI hits carried forward: {len(filename_hits)}",
        f"- Metadata PHI hits carried forward: {len(metadata_hits)}",
        "- Pixel OCR status: NOT RUN BY RELEASE",
        "- AI visual prescreen companion: `clinical_overlay_ai_visual_prescreen.md`",
        "- Final signoff form: `clinical_overlay_signoff_form.md`",
        "- Manual visual review status: REQUIRED",
        "- Clinical-owner signoff status: REQUIRED",
        "",
        "## Visual Review Queue",
        "",
        "| File | Role | Dimensions | SHA256 prefix | Metadata status | Manual visual status | Required pixel checks |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        dims = f"{row['width']}x{row['height']}" if row["width"] and row["height"] else "--"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{escape_md(row['path'])}`",
                    escape_md(row["role"]),
                    escape_md(dims),
                    f"`{escape_md(row['sha256_prefix'] or '--')}`",
                    escape_md(row["metadata_status"]),
                    escape_md(row["manual_visual_status"]),
                    escape_md(row["required_checks"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Required Manual Procedure",
            "",
            "1. Open each queued PNG at full resolution, not only inside the compiled manuscript PDF.",
            "2. Inspect all panel margins, titles, axis labels, annotations, legends, and CT/OAR/CTV pixel regions for burned-in identifiers.",
            "3. Confirm no patient name, MRN, accession number, DOB, full service date, scanner/PACS overlay, institutional label, or patient-identifying free text is visible.",
            "4. Recheck the rendered PDF after compilation because cropping, scaling, or page placement can expose previously overlooked pixels.",
            "5. Record final clinical-owner signoff outside this generated packet before real upload.",
            "6. Record the row-level final decision in `clinical_overlay_signoff_form.md` so regeneration preserves the human signoff state.",
            "",
            "## Evidence Inputs",
            "",
            "- `figure_privacy_integrity_audit.md` records figure hashes, dimensions, filename PHI hits, metadata PHI hits, and which files require clinical pixel review.",
            "- `clinical_overlay_ai_visual_prescreen.md` records an AI-assisted visual precheck after anonymized-title regeneration, but it does not replace clinical-owner signoff.",
            "- `clinical_overlay_signoff_form.md` is the preserved final human signoff record for queued overlay figures.",
            "- `reports/vsi_figure_privacy_integrity_audit_20260531.csv` is the machine-readable input for this packet.",
            "- `reports/vsi_clinical_overlay_visual_review_packet_20260531.csv` contains the same manual review queue in spreadsheet form.",
            "- `reports/vsi_clinical_overlay_ai_visual_prescreen_20260531.csv` contains the machine-readable AI visual prescreen rows.",
            "- `reports/vsi_clinical_overlay_signoff_20260531.csv` contains the machine-readable final signoff audit rows.",
            "",
            "## Completion Rule",
            "",
            "This packet is complete as a visual-review queue only. The AI visual prescreen is a companion precheck, not a signoff. The submission remains blocked until the corresponding author, submitting author, or clinical data owner records every queued clinical overlay image as approved in `clinical_overlay_signoff_form.md` after full-resolution PNG and rendered-PDF inspection.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    write_markdown(rows)
    missing = [row for row in rows if row["exists"] != "YES" or row["readable_status"] != "PASS"]
    filename_hits = [row for row in rows if row["filename_phi_hits"]]
    metadata_hits = [row for row in rows if row["metadata_phi_hits"]]
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(
        "Clinical overlay visual review packet: "
        f"queued={len(rows)}; missing_or_unreadable={len(missing)}; "
        f"filename_phi_hits={len(filename_hits)}; metadata_phi_hits={len(metadata_hits)}"
    )


if __name__ == "__main__":
    main()
