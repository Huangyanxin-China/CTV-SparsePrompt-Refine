#!/usr/bin/env python3
"""Build Gen3/DRS manifests from a TCIA Gen3/GC manifest CSV."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("public_data/glis_rt/GC_manifest_GLIS-RT_20260326.csv"),
    )
    parser.add_argument("--out-dir", type=Path, default=Path("public_data/glis_rt/manifests"))
    parser.add_argument("--prefix", default="glis_rt")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.csv.open()))
    if not rows:
        raise SystemExit(f"No rows in {args.csv}")

    def object_id(row: dict[str, str]) -> str:
        file_id = row["File ID"].strip()
        if not file_id.startswith("dg.4DFC/"):
            raise ValueError(f"Unexpected File ID: {file_id}")
        return file_id

    all_manifest = [{"object_id": object_id(row)} for row in rows]
    (args.out_dir / f"{args.prefix}_all_gen3_manifest.json").write_text(
        json.dumps(all_manifest, indent=2)
    )

    by_modality: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_modality.setdefault(row["Image Modality"].strip(), []).append(row)

    for modality, modality_rows in sorted(by_modality.items()):
        manifest = [{"object_id": object_id(row)} for row in modality_rows]
        (args.out_dir / f"{args.prefix}_{modality.lower()}_gen3_manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )

    summary = {
        "csv": str(args.csv),
        "rows": len(rows),
        "patients": len({row["Participant ID"] for row in rows}),
        "modalities": dict(Counter(row["Image Modality"] for row in rows)),
        "outputs": sorted(p.name for p in args.out_dir.glob("*.json")),
    }
    (args.out_dir / "manifest_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
