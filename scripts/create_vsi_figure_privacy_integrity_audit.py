#!/usr/bin/env python3
"""Audit manuscript figure files for integrity and metadata-level PHI risk."""

from __future__ import annotations

import csv
import hashlib
import re
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "manuscript_vsi_biomedical_data" / "figures"
MD_OUT = ROOT / "manuscript_vsi_biomedical_data" / "figure_privacy_integrity_audit.md"
CSV_OUT = ROOT / "reports" / "vsi_figure_privacy_integrity_audit_20260531.csv"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PHI_PATTERNS = [
    r"\bMRN\b",
    r"medical record",
    r"patient[_ -]?(id|name|number)",
    r"\bDOB\b",
    r"date of birth",
    r"\b\d{3}[- ]\d{2}[- ]\d{4}\b",
    r"\b\d{2}/\d{2}/\d{4}\b",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
]
CLINICAL_FIGURE_HINTS = [
    "baseline_ctv_overlay",
    "baseline_oar_overlay",
    "sammed3d_sparse_prompt",
    "our_sdf_k7",
]


def sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def png_chunks(path: Path) -> tuple[int | None, int | None, list[str], list[str]]:
    width = None
    height = None
    chunk_types: list[str] = []
    text_items: list[str] = []
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        return width, height, chunk_types, text_items
    pos = len(PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8].decode("latin1")
        payload = data[pos + 8 : pos + 8 + length]
        chunk_types.append(ctype)
        if ctype == "IHDR" and length >= 8:
            width, height = struct.unpack(">II", payload[:8])
        elif ctype == "tEXt":
            text_items.append(payload.decode("latin1", errors="ignore"))
        elif ctype == "zTXt":
            key, _, compressed = payload.partition(b"\x00")
            if compressed:
                method = compressed[:1]
                body = compressed[1:]
                if method == b"\x00":
                    try:
                        text = key.decode("latin1", errors="ignore") + "=" + zlib.decompress(body).decode("utf-8", errors="ignore")
                        text_items.append(text)
                    except zlib.error:
                        text_items.append(key.decode("latin1", errors="ignore") + "=<zTXt decompress failed>")
        elif ctype == "iTXt":
            parts = payload.split(b"\x00", 4)
            if len(parts) >= 5:
                key = parts[0].decode("utf-8", errors="ignore")
                compressed_flag = parts[1]
                text_payload = parts[-1]
                if compressed_flag == b"\x01":
                    try:
                        text_payload = zlib.decompress(text_payload)
                    except zlib.error:
                        text_payload = b"<iTXt decompress failed>"
                text_items.append(key + "=" + text_payload.decode("utf-8", errors="ignore"))
        pos += 12 + length
        if ctype == "IEND":
            break
    return width, height, chunk_types, text_items


def pdf_text_probe(path: Path) -> list[str]:
    data = path.read_bytes()
    strings = re.findall(rb"[\x20-\x7E]{5,}", data)
    decoded = [item.decode("latin1", errors="ignore") for item in strings]
    return [item for item in decoded if any(token in item.lower() for token in ["author", "title", "subject", "patient", "mrn", "dob"])]


def phi_hits(text: str) -> list[str]:
    hits = []
    for pattern in PHI_PATTERNS:
        if re.search(pattern, text, re.I):
            hits.append(pattern)
    return hits


def row_for(path: Path) -> dict[str, str]:
    rel = path.relative_to(ROOT).as_posix()
    suffix = path.suffix.lower()
    size = path.stat().st_size
    file_hash = sha256_prefix(path)
    filename_hits = phi_hits(path.name)
    metadata_items: list[str] = []
    chunk_summary = ""
    width = ""
    height = ""
    readable = "PASS"
    if suffix == ".png":
        png_width, png_height, chunks, text_items = png_chunks(path)
        width = str(png_width or "")
        height = str(png_height or "")
        chunk_summary = ",".join(sorted(set(chunks)))
        metadata_items.extend(text_items)
        if not png_width or not png_height:
            readable = "FAIL"
    elif suffix == ".pdf":
        metadata_items.extend(pdf_text_probe(path))
        chunk_summary = "pdf"
    else:
        readable = "WARNING"
        chunk_summary = "unhandled"

    metadata_blob = "\n".join(metadata_items)
    metadata_hits = phi_hits(metadata_blob)
    clinical_hint = any(hint in path.name for hint in CLINICAL_FIGURE_HINTS)
    status = "PASS" if readable == "PASS" and not filename_hits and not metadata_hits else "FAIL"
    return {
        "path": rel,
        "type": suffix.lstrip("."),
        "bytes": str(size),
        "sha256_prefix": file_hash,
        "width": width,
        "height": height,
        "readable_status": readable,
        "chunk_or_probe_summary": chunk_summary,
        "text_metadata_count": str(len(metadata_items)),
        "filename_phi_hits": "; ".join(filename_hits),
        "metadata_phi_hits": "; ".join(metadata_hits),
        "clinical_pixel_review_required": "YES" if clinical_hint else "NO",
        "audit_status": status,
    }


def write_csv(rows: list[dict[str, str]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "path",
        "type",
        "bytes",
        "sha256_prefix",
        "width",
        "height",
        "readable_status",
        "chunk_or_probe_summary",
        "text_metadata_count",
        "filename_phi_hits",
        "metadata_phi_hits",
        "clinical_pixel_review_required",
        "audit_status",
    ]
    with CSV_OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, str]]) -> None:
    failures = [row for row in rows if row["audit_status"] != "PASS"]
    filename_hits = [row for row in rows if row["filename_phi_hits"]]
    metadata_hits = [row for row in rows if row["metadata_phi_hits"]]
    clinical_review = [row for row in rows if row["clinical_pixel_review_required"] == "YES"]
    png_rows = [row for row in rows if row["type"] == "png"]
    pdf_rows = [row for row in rows if row["type"] == "pdf"]
    lines = [
        "# Figure Privacy and Integrity Audit",
        "",
        "This audit checks figure file inventory, hashes, dimensions, PNG textual metadata, PDF metadata probes, and metadata-level PHI risk. It does not perform pixel-level OCR or replace final author visual inspection of clinical panels.",
        "",
        "## Summary",
        "",
        f"- Figure files audited: {len(rows)}",
        f"- PNG files: {len(png_rows)}",
        f"- PDF files: {len(pdf_rows)}",
        f"- Filename PHI hits: {len(filename_hits)}",
        f"- Metadata PHI hits: {len(metadata_hits)}",
        f"- Integrity/metadata failures: {len(failures)}",
        f"- Clinical image panels requiring final visual review: {len(clinical_review)}",
        "- Pixel OCR status: NOT RUN",
        "- Final author visual review status: REQUIRED",
        "",
        "## File Inventory",
        "",
        "| File | Type | Size | SHA256 prefix | Dimensions | Text metadata | Clinical pixel review | Status |",
        "| --- | --- | ---: | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        dims = f"{row['width']}x{row['height']}" if row["width"] and row["height"] else "--"
        lines.append(
            f"| `{row['path']}` | {row['type']} | {row['bytes']} | `{row['sha256_prefix']}` | {dims} | {row['text_metadata_count']} | {row['clinical_pixel_review_required']} | {row['audit_status']} |"
        )
    lines.extend(
        [
            "",
            "## PHI Metadata Scan",
            "",
            f"- Filename PHI hits: {len(filename_hits)}",
            f"- Text/PDF metadata PHI hits: {len(metadata_hits)}",
            "- Pixel-level PHI status: NOT VERIFIED BY THIS SCRIPT",
            "",
            "## Interpretation",
            "",
            "- PASS means the file is readable, has no filename-level PHI pattern hit, and has no textual metadata PHI pattern hit.",
            "- Clinical overlay PNGs still require manual visual inspection because PHI can be rendered into pixels without appearing in metadata.",
            "- Final upload should use this audit together with author visual review of all clinical image panels.",
            "",
        ]
    )
    MD_OUT.write_text("\n".join(lines))


def main() -> None:
    files = sorted(path for path in FIG_DIR.iterdir() if path.is_file() and path.suffix.lower() in {".png", ".pdf"})
    rows = [row_for(path) for path in files]
    write_csv(rows)
    write_markdown(rows)
    failures = [row for row in rows if row["audit_status"] != "PASS"]
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Figure files audited: {len(rows)}; integrity/metadata failures: {len(failures)}")
    if failures:
        for row in failures:
            print(f"FAIL {row['path']}: filename={row['filename_phi_hits']} metadata={row['metadata_phi_hits']}")


if __name__ == "__main__":
    main()
