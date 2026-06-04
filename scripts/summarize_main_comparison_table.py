import argparse
import glob
import os

import pandas as pd


def read_direct(path, method_name):
    if not path or not os.path.exists(path):
        return []
    df = pd.read_csv(path)
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "comparison_method": method_name,
                "case_id": r["case_id"],
                "prompt_mode": "",
                "supervision": "none",
                "dice": r.get("dice"),
                "dice_annotated": "",
                "dice_unannotated": "",
                "hd95": r.get("hd95"),
                "asd": r.get("asd"),
                "pred_foreground": r.get("pred_foreground"),
                "gt_foreground": r.get("gt_foreground"),
                "source_file": path,
            }
        )
    return rows


def read_sam(pattern):
    rows = []
    for path in sorted(glob.glob(pattern)):
        df = pd.read_csv(path)
        parts = path.split(os.sep)
        branch = parts[-2] if len(parts) >= 2 else ""
        if branch.startswith("zeroshot"):
            supervision = "none"
            method = f"SAM {branch}"
        elif branch.startswith("finetune"):
            supervision = "sparse 2D slices"
            method = f"SAM {branch}"
        else:
            supervision = ""
            method = f"SAM {branch}"
        for _, r in df.iterrows():
            rows.append(
                {
                    "comparison_method": method,
                    "case_id": r["case_id"],
                    "prompt_mode": r.get("prompt_mode", ""),
                    "supervision": supervision,
                    "dice": r.get("dice"),
                    "dice_annotated": r.get("dice_annotated", ""),
                    "dice_unannotated": r.get("dice_unannotated", ""),
                    "hd95": r.get("hd95"),
                    "asd": r.get("asd"),
                    "pred_foreground": r.get("pred_foreground"),
                    "gt_foreground": r.get("gt_foreground"),
                    "source_file": path,
                }
            )
    return rows


def main():
    parser = argparse.ArgumentParser(description="Summarize main direct-pseudo vs SAM comparison table.")
    parser.add_argument("--direct_metrics", default="results/sdf_ns3_largest_metrics.csv")
    parser.add_argument("--direct_name", default="Direct pseudo (SDF)")
    parser.add_argument("--sam_glob", default="results/sam_sparse/single_case/*/*/metrics_summary.csv")
    parser.add_argument("--output_csv", default="results/main_comparison_table.csv")
    parser.add_argument("--best_csv", default="results/main_comparison_best_by_case.csv")
    args = parser.parse_args()

    rows = []
    rows.extend(read_direct(args.direct_metrics, args.direct_name))
    rows.extend(read_sam(args.sam_glob))
    if not rows:
        raise SystemExit("No rows found.")
    out = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(args.output_csv), exist_ok=True)
    out.to_csv(args.output_csv, index=False)
    best = out.sort_values("dice", ascending=False).groupby("case_id", as_index=False).head(8)
    best.to_csv(args.best_csv, index=False)
    print(f"Saved: {args.output_csv}")
    print(f"Saved: {args.best_csv}")
    cols = ["case_id", "comparison_method", "prompt_mode", "supervision", "dice", "dice_annotated", "dice_unannotated", "hd95", "asd"]
    print(best[cols].to_string(index=False))


if __name__ == "__main__":
    main()
