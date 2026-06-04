#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_metric(path, case_key="case"):
    out = {}
    with Path(path).open() as f:
        for row in csv.DictReader(f):
            case = row.get(case_key) or row.get("case_id")
            out[case] = row
    return out


def as_float(row, key):
    try:
        return float(row[key])
    except Exception:
        return float("nan")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_csv", default=str(ROOT / "reports" / "ctv_main_per_case_comparison.csv"))
    args = parser.parse_args()

    our = read_metric(ROOT / "results/our_sdf_pseudo_k7_even_from_sam_prompts/per_case_metrics.csv")
    nnunet = read_metric(ROOT / "external_runs/metrics/nnunet_3d_fullres_folds012_final/ctv/per_case.csv")
    diffunet = read_metric(ROOT / "external_runs/metrics/diffunet/ctv/per_case.csv")
    sam_sparse = read_metric(ROOT / "external_runs/metrics/sammed3d_sparse_prompt_k7_even_nonempty_click7/ctv/per_case.csv")
    sam_ct = read_metric(ROOT / "external_runs/metrics/sammed3d_nonoracle_ct_heuristic_click1/ctv/per_case.csv")

    rows = []
    for case in sorted(our):
        r = our[case]
        our_dice = as_float(r, "dice")
        row = {
            "case": case,
            "our_sdf_dice": our_dice,
            "our_sdf_unseen_dice": as_float(r, "dice_unseen_slices"),
            "our_sdf_hd95": as_float(r, "hd95"),
            "our_sdf_asd": as_float(r, "asd"),
            "our_sdf_volume_diff_percent": as_float(r, "volume_diff_percent"),
            "nnunet_dice": as_float(nnunet.get(case, {}), "dice"),
            "diffunet_dice": as_float(diffunet.get(case, {}), "dice"),
            "sam_sparse_k7_dice": as_float(sam_sparse.get(case, {}), "dice"),
            "sam_ct_derived_dice": as_float(sam_ct.get(case, {}), "dice"),
        }
        row["delta_vs_nnunet"] = row["our_sdf_dice"] - row["nnunet_dice"]
        row["delta_vs_diffunet"] = row["our_sdf_dice"] - row["diffunet_dice"]
        row["delta_vs_sam_sparse_k7"] = row["our_sdf_dice"] - row["sam_sparse_k7_dice"]
        row["delta_vs_sam_ct_derived"] = row["our_sdf_dice"] - row["sam_ct_derived_dice"]
        rows.append(row)

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case",
        "our_sdf_dice",
        "our_sdf_unseen_dice",
        "our_sdf_hd95",
        "our_sdf_asd",
        "our_sdf_volume_diff_percent",
        "nnunet_dice",
        "diffunet_dice",
        "sam_sparse_k7_dice",
        "sam_ct_derived_dice",
        "delta_vs_nnunet",
        "delta_vs_diffunet",
        "delta_vs_sam_sparse_k7",
        "delta_vs_sam_ct_derived",
    ]
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("Wrote", out_csv)
    for key in ("delta_vs_nnunet", "delta_vs_diffunet", "delta_vs_sam_sparse_k7", "delta_vs_sam_ct_derived"):
        vals = [row[key] for row in rows]
        print(key, "mean", sum(vals) / len(vals), "improved", sum(v > 0 for v in vals), "/", len(vals))


if __name__ == "__main__":
    main()
