#!/usr/bin/env python3
import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/share3/home/huangyanxin/DiffUNet-main")
    parser.add_argument("--raw_dataset", required=True)
    parser.add_argument("--image_dir", required=True)
    parser.add_argument("--label_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--work_dir", required=True)
    parser.add_argument("--labels", nargs="+", type=int, required=True)
    parser.add_argument("--spacing", nargs=3, type=float, default=None)
    parser.add_argument("--num_processes", type=int, default=8)
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    sys.path.insert(0, repo)

    from light_training.preprocessing.preprocessors.default_preprocessor import DefaultPreprocessor

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)
    os.chdir(args.work_dir)

    preprocessor = DefaultPreprocessor(
        base_dir=os.path.abspath(args.raw_dataset),
        image_dir=args.image_dir,
        label_dir=args.label_dir,
    )

    analysis_path = os.path.join(args.work_dir, "data_analysis_result.txt")
    if not os.path.exists(analysis_path):
        preprocessor.run_plan()

    if args.spacing is None:
        with open(analysis_path) as f:
            analysis = json.load(f)
        output_spacing = analysis["fullres spacing"]
    else:
        output_spacing = args.spacing

    with open(analysis_path) as f:
        analysis = json.load(f)
    intensity_props = analysis["intensity_statistics_per_channel"]

    preprocessor.run(
        output_spacing=output_spacing,
        output_dir=os.path.abspath(args.output_dir),
        all_labels=args.labels,
        foreground_intensity_properties_per_channel=intensity_props,
        num_processes=args.num_processes,
    )


if __name__ == "__main__":
    main()
