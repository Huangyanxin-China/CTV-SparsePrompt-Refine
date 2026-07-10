import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "scripts/evaluate_segmentation_folder.py"


def write_mask(path: Path, array: np.ndarray, origin=(0.0, 0.0, 0.0)):
    image = sitk.GetImageFromArray(array.astype(np.uint8))
    image.SetSpacing((1.0, 1.0, 2.0))
    image.SetOrigin(origin)
    sitk.WriteImage(image, str(path))


def evaluator_command(gt_dir: Path, pred_dir: Path, output_dir: Path):
    return [
        sys.executable,
        str(EVALUATOR),
        "--gt_dir",
        str(gt_dir),
        "--pred_dir",
        str(pred_dir),
        "--classes",
        "1",
        "--output_csv",
        str(output_dir / "metrics.csv"),
        "--output_json",
        str(output_dir / "metrics.json"),
        "--skip_surface_metrics",
    ]


def test_evaluator_smoke_with_identical_prediction(tmp_path):
    gt_dir = tmp_path / "gt"
    pred_dir = tmp_path / "pred"
    out_dir = tmp_path / "out"
    gt_dir.mkdir()
    pred_dir.mkdir()
    out_dir.mkdir()

    mask = np.zeros((4, 8, 8), dtype=np.uint8)
    mask[1:3, 2:6, 2:6] = 1
    write_mask(gt_dir / "case_001.nii.gz", mask)
    write_mask(pred_dir / "case_001.nii.gz", mask)

    result = subprocess.run(
        evaluator_command(gt_dir, pred_dir, out_dir),
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((out_dir / "metrics.json").read_text())
    assert summary["num_ground_truth"] == 1
    assert summary["num_evaluated_cases"] == 1
    assert summary["macro_class_case"]["dice"]["mean"] == 1.0


def test_evaluator_rejects_missing_prediction(tmp_path):
    gt_dir = tmp_path / "gt"
    pred_dir = tmp_path / "pred"
    out_dir = tmp_path / "out"
    gt_dir.mkdir()
    pred_dir.mkdir()
    out_dir.mkdir()

    mask = np.zeros((4, 8, 8), dtype=np.uint8)
    mask[1:3, 2:6, 2:6] = 1
    write_mask(gt_dir / "case_001.nii.gz", mask)
    write_mask(gt_dir / "case_002.nii.gz", mask)
    write_mask(pred_dir / "case_001.nii.gz", mask)

    result = subprocess.run(
        evaluator_command(gt_dir, pred_dir, out_dir),
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "Missing predictions" in result.stderr


def test_evaluator_rejects_geometry_mismatch(tmp_path):
    gt_dir = tmp_path / "gt"
    pred_dir = tmp_path / "pred"
    out_dir = tmp_path / "out"
    gt_dir.mkdir()
    pred_dir.mkdir()
    out_dir.mkdir()

    mask = np.zeros((4, 8, 8), dtype=np.uint8)
    mask[1:3, 2:6, 2:6] = 1
    write_mask(gt_dir / "case_001.nii.gz", mask)
    write_mask(
        pred_dir / "case_001.nii.gz",
        mask,
        origin=(1.0, 0.0, 0.0),
    )

    result = subprocess.run(
        evaluator_command(gt_dir, pred_dir, out_dir),
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "geometry mismatch" in result.stderr.lower()
