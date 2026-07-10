import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = [
    "scripts/run_sparse_prompt_core_envelope_workflow.py",
    "scripts/run_k7_preprocess_variant_screen.py",
    "scripts/run_traditional_linear_mask_interpolation_baseline.py",
    "scripts/train_ctv_pseudo_refine_net.py",
    "scripts/evaluate_segmentation_folder.py",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_public_cli_help(script):
    result = subprocess.run(
        [sys.executable, str(ROOT / script), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
