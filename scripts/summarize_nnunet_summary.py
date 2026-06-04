#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def load_label_map(dataset_json_path: Path) -> dict[str, str]:
    dataset = json.loads(dataset_json_path.read_text())
    labels = dataset["labels"]
    result: dict[str, str] = {}
    for key, value in labels.items():
        if isinstance(value, int):
            result[str(value)] = key
        elif isinstance(key, str) and key.isdigit():
            result[key] = str(value)
        else:
            result[str(value)] = str(key)
    return result


def metric_value(metrics: dict, key: str):
    value = metrics.get(key, "")
    if isinstance(value, float):
        return f"{value:.8f}"
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize nnU-Net evaluate_folder summary.json into class and case CSV files."
    )
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--dataset-json", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--target-label", default="5")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary = json.loads(args.summary.read_text())
    label_map = load_label_map(args.dataset_json)

    metric_keys = ["Dice", "IoU", "TP", "FP", "FN", "TN", "n_pred", "n_ref"]

    class_csv = args.out_dir / "metrics_per_class.csv"
    with class_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["label_id", "label_name", *metric_keys])
        for label_id, metrics in sorted(summary.get("mean", {}).items(), key=lambda item: int(item[0])):
            writer.writerow([
                label_id,
                label_map.get(str(label_id), ""),
                *[metric_value(metrics, key) for key in metric_keys],
            ])

    case_csv = args.out_dir / "metrics_per_case.csv"
    ctv_csv = args.out_dir / "ctv_case_metrics.csv"
    with case_csv.open("w", newline="") as f_all, ctv_csv.open("w", newline="") as f_ctv:
        all_writer = csv.writer(f_all)
        ctv_writer = csv.writer(f_ctv)
        header = ["case_id", "prediction_file", "reference_file", "label_id", "label_name", *metric_keys]
        all_writer.writerow(header)
        ctv_writer.writerow(header)

        for item in summary.get("metric_per_case", []):
            prediction_file = item.get("prediction_file", "")
            reference_file = item.get("reference_file", "")
            case_id = Path(prediction_file).name
            if case_id.endswith(".nii.gz"):
                case_id = case_id[:-7]
            else:
                case_id = Path(prediction_file).stem

            for label_id, metrics in sorted(item.get("metrics", {}).items(), key=lambda pair: int(pair[0])):
                row = [
                    case_id,
                    prediction_file,
                    reference_file,
                    label_id,
                    label_map.get(str(label_id), ""),
                    *[metric_value(metrics, key) for key in metric_keys],
                ]
                all_writer.writerow(row)
                if str(label_id) == str(args.target_label):
                    ctv_writer.writerow(row)

    print(f"Wrote {class_csv}")
    print(f"Wrote {case_csv}")
    print(f"Wrote {ctv_csv}")


if __name__ == "__main__":
    main()
