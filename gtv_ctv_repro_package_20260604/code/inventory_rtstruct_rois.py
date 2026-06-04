from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import pydicom

from scan_gtv_cases import ROOT, find_uid_file, referenced_structure_uids


GTV_CSV = ROOT / "gtv_cases.csv"


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def patient_from_path(path: Path) -> tuple[str, str]:
    parts = path.relative_to(ROOT).parts
    batch = parts[0] if len(parts) > 0 else ""
    patient = ""
    for part in parts:
        if part.startswith("patient_"):
            patient = part
            break
    return batch, patient


def roi_names(path: Path) -> list[str]:
    ds = pydicom.dcmread(str(path), force=True, stop_before_pixels=True)
    names: list[str] = []
    for item in getattr(ds, "StructureSetROISequence", []) or []:
        name = as_text(getattr(item, "ROIName", "")).strip()
        if name:
            names.append(name)
    return names


def unique_gtv_structures() -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    with GTV_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            path = Path(row["structure_file"])
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return sorted(paths, key=str)


def all_referenced_structures() -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for batch in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        for patient in sorted(p for p in batch.iterdir() if p.is_dir()):
            plan_dir = patient / "DICOM_PLAN"
            ct_dir = patient / "CT_SET"
            if not plan_dir.is_dir() or not ct_dir.is_dir():
                continue
            for plan_path in sorted(p for p in plan_dir.rglob("*") if p.is_file()):
                try:
                    plan_ds = pydicom.dcmread(str(plan_path), force=True, stop_before_pixels=True)
                except Exception:
                    continue
                if as_text(getattr(plan_ds, "Modality", "")).strip() != "RTPLAN":
                    continue
                for uid in referenced_structure_uids(plan_ds):
                    struct_path = find_uid_file(ct_dir, uid)
                    if struct_path and struct_path not in seen:
                        seen.add(struct_path)
                        paths.append(struct_path)
    return sorted(paths, key=str)


def category(name: str) -> str:
    s = name.casefold()
    rules = [
        ("GTV", [r"gtv", r"大体肿瘤", r"肿瘤靶区"]),
        ("CTV", [r"ctv", r"临床靶区"]),
        ("Lung", [r"lung", r"pulmo", r"肺"]),
        ("Heart", [r"heart", r"cardiac", r"pericard", r"心"]),
        ("SpinalCord", [r"spinal", r"cord", r"myelon", r"脊髓"]),
        ("Esophagus", [r"esoph", r"oesoph", r"(^|[^a-z0-9])eso([^a-z0-9]|$)", r"食管"]),
        ("PTV", [r"ptv"]),
        ("Body/External/Skin", [r"body", r"external", r"skin", r"outline", r"kbody"]),
        ("Ring/DoseControl", [r"ring", r"dose", r"control", r"opt", r"avoid"]),
        ("Airway/Trachea/Bronchus", [r"trache", r"bronch", r"airway", r"气管", r"支气管"]),
        ("Vessels/Aorta", [r"aorta", r"vessel", r"artery", r"vena", r"svc", r"ivc", r"血管", r"主动脉"]),
        ("Bone/Rib/Vertebra", [r"bone", r"rib", r"verte", r"spine", r"骨", r"肋"]),
        ("Breast/ChestWall", [r"breast", r"chestwall", r"chest wall", r"胸壁", r"乳"]),
        ("Liver/Stomach/Spleen/Kidney", [r"liver", r"stomach", r"spleen", r"kidney", r"肝", r"胃", r"脾", r"肾"]),
        ("Thyroid", [r"thyroid", r"甲状腺"]),
        ("PRV/Margin", [r"prv", r"margin"]),
        ("Couch/Support/Bolus", [r"couch", r"table", r"support", r"bolus", r"床"]),
    ]
    for label, patterns in rules:
        if any(re.search(pattern, s, flags=re.IGNORECASE) for pattern in patterns):
            return label
    return "Other"


def write_inventory(scope: str, paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        batch, patient = patient_from_path(path)
        try:
            names = roi_names(path)
        except Exception as exc:
            rows.append(
                {
                    "scope": scope,
                    "batch": batch,
                    "patient": patient,
                    "structure_file": str(path),
                    "roi_name": "",
                    "category": "READ_ERROR",
                    "error": str(exc),
                }
            )
            continue
        for name in names:
            rows.append(
                {
                    "scope": scope,
                    "batch": batch,
                    "patient": patient,
                    "structure_file": str(path),
                    "roi_name": name,
                    "category": category(name),
                    "error": "",
                }
            )
    return rows


def summarize(scope: str, rows: list[dict[str, str]]) -> None:
    scope_rows = [r for r in rows if r["scope"] == scope and r["roi_name"]]
    structures = {r["structure_file"] for r in scope_rows}
    patients = {(r["batch"], r["patient"]) for r in scope_rows}
    excluded = {"GTV", "CTV", "Heart", "Lung", "SpinalCord"}
    other_rows = [r for r in scope_rows if r["category"] not in excluded]

    print(f"\n=== {scope} ===")
    print(f"RTSTRUCT files: {len(structures)}")
    print(f"Patients: {len(patients)}")
    print(f"Total ROI entries: {len(scope_rows)}")
    print(f"Other ROI entries excluding GTV/CTV/Heart/Lung/SpinalCord: {len(other_rows)}")

    cat_counts = Counter(r["category"] for r in other_rows)
    print("Other categories:")
    for cat, count in cat_counts.most_common():
        structure_count = len({r["structure_file"] for r in other_rows if r["category"] == cat})
        print(f"  {cat}: entries={count}, structures={structure_count}")

    name_counts = Counter(r["roi_name"] for r in other_rows)
    print("Top other ROI names:")
    for name, count in name_counts.most_common(60):
        print(f"  {name}: {count}")


def main() -> None:
    gtv_paths = unique_gtv_structures()
    all_paths = all_referenced_structures()

    all_rows = []
    all_rows.extend(write_inventory("gtv_cases", gtv_paths))
    all_rows.extend(write_inventory("all_rtstructs", all_paths))

    inventory_csv = ROOT / "roi_inventory.csv"
    with inventory_csv.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["scope", "batch", "patient", "structure_file", "roi_name", "category", "error"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    for scope in ("gtv_cases", "all_rtstructs"):
        summarize(scope, all_rows)

    print(f"\nCSV: {inventory_csv}")


if __name__ == "__main__":
    main()
