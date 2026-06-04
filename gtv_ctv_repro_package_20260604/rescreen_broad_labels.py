from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import pydicom

from export_gtv_rtstruct_masks import CATEGORY_RULES, match_categories, roi_number_to_name
from inventory_rtstruct_rois import all_referenced_structures, unique_gtv_structures


ROOT = Path(__file__).resolve().parent
OUT_CSV = ROOT / "broad_label_rescreen.csv"


def normalize(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", name).casefold()


def broad_categories(name: str) -> set[str]:
    raw = name.casefold()
    compact = normalize(name)
    cats: set[str] = set()

    if "gtv" in compact or "大体肿瘤" in raw or "肿瘤靶区" in raw:
        cats.add("GTV")
    if "ctv" in compact or "临床靶区" in raw:
        cats.add("CTV")
    if "lung" in compact or "pulmo" in compact or "肺" in raw:
        cats.add("Lung")
    if "heart" in compact or "cardiac" in compact or "pericard" in compact or "心" in raw:
        cats.add("Heart")
    if "spinalcord" in compact or "spinal" in compact or "cord" in compact or "myelon" in compact or "脊髓" in raw:
        cats.add("SpinalCord")
    if "esoph" in compact or "oesoph" in compact or re.search(r"(^|[^a-z0-9])eso([^a-z0-9]|$)", raw) or "食管" in raw:
        cats.add("Esophagus")
    return cats


def current_categories(name: str) -> set[str]:
    cats = set()
    for category, rule in CATEGORY_RULES.items():
        if any(re.search(pattern, name.casefold(), flags=re.IGNORECASE) for pattern in rule["patterns"]):
            cats.add(category)
    return cats


def scan(scope: str, paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        ds = pydicom.dcmread(str(path), force=True, stop_before_pixels=True)
        roi_map = roi_number_to_name(ds)
        for _, name in roi_map.items():
            current = current_categories(name)
            broad = broad_categories(name)
            rows.append(
                {
                    "scope": scope,
                    "structure_file": str(path),
                    "roi_name": name,
                    "current_categories": ";".join(sorted(current)),
                    "broad_categories": ";".join(sorted(broad)),
                    "new_categories": ";".join(sorted(broad - current)),
                }
            )
    return rows


def summarize(scope: str, rows: list[dict[str, str]]) -> None:
    scope_rows = [r for r in rows if r["scope"] == scope]
    structures = {r["structure_file"] for r in scope_rows}
    print(f"\n=== {scope} ===")
    print(f"RTSTRUCT files: {len(structures)}")

    for mode in ("current_categories", "broad_categories"):
        print(f"{mode}:")
        for category in ["GTV", "CTV", "Lung", "Heart", "SpinalCord", "Esophagus"]:
            matched = [r for r in scope_rows if category in r[mode].split(";")]
            matched_structures = {r["structure_file"] for r in matched}
            names = Counter(r["roi_name"] for r in matched)
            print(f"  {category}: structures={len(matched_structures)}, roi_entries={len(matched)}")
            if names:
                print("    top names: " + "; ".join(f"{n} ({c})" for n, c in names.most_common(10)))

    new_rows = [r for r in scope_rows if r["new_categories"]]
    print(f"new broad-only ROI entries: {len(new_rows)}")
    if new_rows:
        by_cat: dict[str, Counter[str]] = defaultdict(Counter)
        for r in new_rows:
            for cat in r["new_categories"].split(";"):
                by_cat[cat][r["roi_name"]] += 1
        for cat, counter in sorted(by_cat.items()):
            print(f"  {cat}: " + "; ".join(f"{n} ({c})" for n, c in counter.most_common(20)))


def main() -> None:
    rows = []
    rows.extend(scan("gtv_cases", unique_gtv_structures()))
    rows.extend(scan("all_rtstructs", all_referenced_structures()))

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scope",
                "structure_file",
                "roi_name",
                "current_categories",
                "broad_categories",
                "new_categories",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    summarize("gtv_cases", rows)
    summarize("all_rtstructs", rows)
    print(f"\nCSV: {OUT_CSV}")


if __name__ == "__main__":
    main()
