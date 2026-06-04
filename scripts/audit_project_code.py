#!/usr/bin/env python3
"""Lightweight repeatable audit for project-owned code.

This script intentionally avoids training, downloading data, or full-cohort
inference. It checks syntax, simple unused imports, command entry points,
generated-report integrity, and obvious cleanliness issues such as Python
bytecode caches.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ("scripts", "models", "utils", "python_compat")
DEFAULT_UMAMBA_PYTHON = Path("/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python")

HELP_SCRIPTS = (
    "scripts/run_sparse_prompt_core_envelope_workflow.py",
    "scripts/run_k7_preprocess_variant_screen.py",
    "scripts/run_traditional_linear_mask_interpolation_baseline.py",
    "scripts/export_best_ctv_method_vs_baseline_html.py",
)

REQUIRED_ARTIFACTS = (
    "README.md",
    ".gitignore",
    "docs/method_implementation_code_locations_20260604.md",
    "docs/github_cleanup_audit_20260604.md",
    "manuscript_pr_biomedical_data_refine_20260603/main.tex",
    "manuscript_pr_biomedical_data_refine_20260603/figures/gtv_ctv_difference_example.png",
    "manuscript_pr_biomedical_data_refine_20260603/figures/method_visual_comparison_example.png",
    "manuscript_pr_biomedical_data_refine_20260603/figures/ablation_visual_progression_example.png",
)
HISTORICAL_ARCHIVE_MANIFEST = ROOT / "docs/historical_experiment_archive_manifest.csv"
ABSOLUTE_PATH_PATTERN = re.compile(r"/share3/home/huangyanxin[^\s\"'\)\]\[,;}`]+")

CURRENT_METHOD_SCRIPTS = {
    "run_sparse_prompt_core_envelope_workflow.py",
    "run_k7_preprocess_variant_screen.py",
    "run_traditional_linear_mask_interpolation_baseline.py",
    "export_best_ctv_method_vs_baseline_html.py",
    "generate_sdf_pseudo_from_sparse_prompts.py",
    "run_data_preprocess_chooser_k7.py",
    "run_next_sparse_prompt_experiments_server05.sh",
    "summarize_k7_variant_surface.py",
    "train_ctv_pseudo_refine_net.py",
    "run_ctv_pseudo_refine_net_gpu1.sh",
    "evaluate_ctv_refine_safety_fusion.py",
}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_command(cmd: list[str], timeout: int = 120) -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "ok": False,
            "timeout": timeout,
        }


def python_files() -> list[Path]:
    paths: list[Path] = []
    for dirname in CODE_DIRS:
        root = ROOT / dirname
        if root.exists():
            paths.extend(sorted(root.rglob("*.py")))
    return paths


def shell_files() -> list[Path]:
    scripts = ROOT / "scripts"
    if not scripts.exists():
        return []
    return sorted(scripts.rglob("*.sh"))


def script_inventory_files() -> list[Path]:
    scripts = ROOT / "scripts"
    if not scripts.exists():
        return []
    files = [
        path
        for path in scripts.iterdir()
        if path.is_file() and path.suffix in {".py", ".sh"}
    ]
    archive = scripts / "archive" / "historical_experiments"
    if archive.exists():
        files.extend(path for path in archive.rglob("*") if path.is_file() and path.suffix in {".py", ".sh"})
    return sorted(files)


def check_python_syntax() -> dict:
    failures = []
    files = python_files()
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - audit should report any parser error.
            failures.append({"path": rel(path), "error": repr(exc)})
    return {"n_files": len(files), "failures": failures, "ok": not failures}


def collect_dunder_all_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            for item in node.value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    names.add(item.value)
    return names


def check_unused_imports() -> dict:
    findings = []
    files = python_files()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used_names = collect_dunder_all_names(tree)

        class UsedNameVisitor(ast.NodeVisitor):
            def visit_Name(self, node: ast.Name) -> None:  # noqa: N802 - ast visitor API.
                used_names.add(node.id)
                self.generic_visit(node)

        UsedNameVisitor().visit(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if name not in used_names:
                        findings.append(
                            {
                                "path": rel(path),
                                "line": node.lineno,
                                "import": alias.name,
                                "bound_name": name,
                            }
                        )
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    name = alias.asname or alias.name
                    if name not in used_names:
                        findings.append(
                            {
                                "path": rel(path),
                                "line": node.lineno,
                                "module": node.module,
                                "import": alias.name,
                                "bound_name": name,
                            }
                        )
    return {"n_files": len(files), "findings": findings, "ok": not findings}


def check_shell_syntax() -> dict:
    failures = []
    files = shell_files()
    for path in files:
        result = run_command(["bash", "-n", str(path)], timeout=30)
        if not result["ok"]:
            failures.append({"path": rel(path), "stderr": result["stderr"], "returncode": result["returncode"]})
    return {"n_files": len(files), "failures": failures, "ok": not failures}


def check_shell_references() -> dict:
    pattern = re.compile(r"(?<![\w/.-])(?:\$\{PROJECT_ROOT\}/|\$PROJECT_ROOT/|\./)?scripts/[A-Za-z0-9_./+-]+")
    references = []
    missing = []
    for path in shell_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in pattern.finditer(text):
            raw = match.group(0).strip("\"'`;,:)")
            normalized = raw.replace("${PROJECT_ROOT}/", "").replace("$PROJECT_ROOT/", "")
            if normalized.startswith("./"):
                normalized = normalized[2:]
            target = ROOT / normalized
            row = {"path": rel(path), "reference": raw, "normalized": normalized, "exists": target.exists()}
            references.append(row)
            if not target.exists():
                missing.append(row)
    return {"n_references": len(references), "missing": missing, "ok": not missing}


def classify_script(path: Path) -> tuple[str, str]:
    name = path.name
    if rel(path).startswith("scripts/archive/historical_experiments/"):
        return "historical_experiment", "archived experiment script retained for provenance"
    if name in CURRENT_METHOD_SCRIPTS:
        return "current_method", "canonical sparse-prompt CTV preprocessing workflow"
    if name == "audit_project_code.py":
        return "maintenance", "project audit and cleanliness checks"
    if name == "deploy_to_github_pages.sh":
        return "maintenance", "GitHub repository and user-page deployment helper"
    if name in {"notify_on_completion.sh"}:
        return "utility", "runtime helper"
    if name.startswith(("apply_vsi_", "sync_vsi_", "verify_vsi_", "create_vsi_")):
        return "submission_vsi", "manuscript/submission packaging utility"
    if name.startswith("create_psi_"):
        return "submission_vsi", "paper experiment audit and manuscript visual package"
    if name.startswith(("build_", "check_external_", "download_", "prepare_", "inspect_", "register_mri_", "run_mri_ct_registration")):
        return "data_preparation", "data discovery, conversion, download, or registration"
    if name.startswith(("create_dataset004_", "create_downstream_pseudo_", "create_one_case_train_dataset")):
        return "data_preparation", "nnU-Net dataset construction"
    if name.startswith(("diffunet_", "sammed3d_", "train_sam_", "infer_sam_")):
        return "baseline_segmentation", "external neural-network baseline"
    if name.startswith(("run_dataset", "run_external_seg_", "run_downstream_pseudo_", "run_nnunet_")):
        return "baseline_segmentation", "server/GPU segmentation baseline workflow"
    if name.startswith(("check_network_backbones", "evaluate_segmentation_", "summarize_nnunet_")):
        return "baseline_segmentation", "segmentation baseline verification or summary"
    if name.startswith(("summarize_no_prompt_", "summarize_oar_baselines_", "summarize_completed_segmentation_", "summarize_dice_only_")):
        return "baseline_segmentation", "segmentation result summary"
    if name.startswith(("create_best_method_", "create_method_ppt_", "create_stage_results_")):
        return "report_generation", "method report or presentation generation"
    if name.startswith(("create_baseline_visualizations", "create_ctv_", "create_oar_", "create_our_sdf_", "create_sammed3d_")):
        return "report_generation", "visualization or per-case comparison generation"
    if name.startswith("generate_pr_visual_figures"):
        return "report_generation", "Pattern Recognition manuscript figure generation"
    if name.startswith(("summarize_ctv_", "summarize_current_", "summarize_main_comparison_")):
        return "report_generation", "CTV experiment summary table generation"
    if name.startswith("verify_no_pdf_assets_"):
        return "report_generation", "report package verification"
    if name.startswith(("evaluate_core_envelope", "evaluate_ctv_method_", "evaluate_pseudo")):
        return "historical_experiment", "experiment evaluation helper retained for provenance"
    if name.startswith(("generate_connectivity_", "generate_structure_", "generate_zprop_")):
        return "historical_experiment", "older pseudo-label generation experiment"
    if name.startswith(("validate_", "run_core_envelope_", "run_connectivity_", "run_graphcut_")):
        return "historical_experiment", "ablation or exploratory validation workflow"
    if name.startswith(("run_step1_", "run_structure_", "run_surface_", "run_zprop_", "run_train50_")):
        return "historical_experiment", "older exploratory pseudo-label workflow"
    if name.startswith(("run_slice_selection_", "run_method_validation_", "summarize_method_validation_")):
        return "historical_experiment", "method validation or prompt-selection ablation"
    if name.startswith(("run_doctor_prior_", "run_sam_diagnostic_", "run_sam_sparse_", "run_main_comparison_sam_")):
        return "historical_experiment", "earlier SAM/refinement comparison workflow"
    return "uncategorized", "needs owner review"


def check_script_inventory() -> dict:
    rows = []
    for path in script_inventory_files():
        category, role = classify_script(path)
        rows.append(
            {
                "path": rel(path),
                "type": path.suffix.lstrip("."),
                "category": category,
                "role": role,
            }
        )
    uncategorized = [row for row in rows if row["category"] == "uncategorized"]
    categories: dict[str, int] = {}
    for row in rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1
    return {
        "n_scripts": len(rows),
        "categories": categories,
        "uncategorized": uncategorized,
        "rows": rows,
        "ok": not uncategorized,
    }


def check_script_main_guards() -> dict:
    scripts_dir = ROOT / "scripts"
    missing = []
    python_scripts = sorted(scripts_dir.glob("*.py")) if scripts_dir.exists() else []
    for path in python_scripts:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if 'if __name__ == "__main__"' not in text and "if __name__ == '__main__'" not in text:
            missing.append(rel(path))
    return {"n_python_scripts": len(python_scripts), "missing_main_guard": missing, "ok": not missing}


def check_historical_archive_manifest(script_inventory: dict) -> dict:
    historical_paths = {
        row["path"]
        for row in script_inventory["rows"]
        if row["category"] == "historical_experiment"
    }
    out = {
        "manifest": rel(HISTORICAL_ARCHIVE_MANIFEST),
        "exists": HISTORICAL_ARCHIVE_MANIFEST.exists(),
        "n_historical_scripts": len(historical_paths),
    }
    if not historical_paths and not HISTORICAL_ARCHIVE_MANIFEST.exists():
        out.update({"ok": True, "missing_in_manifest": [], "extra_in_manifest": []})
        return out
    if not HISTORICAL_ARCHIVE_MANIFEST.exists():
        out.update({"ok": False, "missing_in_manifest": sorted(historical_paths), "extra_in_manifest": []})
        return out

    with HISTORICAL_ARCHIVE_MANIFEST.open(newline="") as f:
        rows = list(csv.DictReader(f))
    manifest_paths = {row.get("path", "") for row in rows}
    missing = sorted(historical_paths - manifest_paths)
    extra = sorted(manifest_paths - historical_paths)
    blank_decisions = sorted(row.get("path", "") for row in rows if not row.get("retention_decision"))
    out.update(
        {
            "n_manifest_rows": len(rows),
            "missing_in_manifest": missing,
            "extra_in_manifest": extra,
            "blank_retention_decisions": blank_decisions,
            "ok": not missing and (not extra or not historical_paths) and not blank_decisions,
        }
    )
    return out


def classify_absolute_path(path_text: str) -> str:
    if "CTV_SparsePrompt_Refine" in path_text:
        return "project_path"
    if "miniconda3/envs" in path_text:
        return "python_environment"
    if any(name in path_text for name in ("SAM-Med3D-main", "DiffUNet-main", "U-Mamba", "nnUNet")):
        return "external_code_or_nnunet"
    if "Seg4TV" in path_text:
        return "external_project_or_data"
    if "20260422" in path_text:
        return "local_raw_data"
    return "other_absolute_path"


def check_absolute_path_dependencies() -> dict:
    rows = []
    unknown = []
    project_paths = []
    for dirname in CODE_DIRS:
        root = ROOT / dirname
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                for match in ABSOLUTE_PATH_PATTERN.finditer(line):
                    path_text = match.group(0)
                    category = classify_absolute_path(path_text)
                    row = {
                        "file": rel(path),
                        "line": line_no,
                        "path": path_text,
                        "category": category,
                        "context": line.strip()[:240],
                    }
                    rows.append(row)
                    if category == "other_absolute_path":
                        unknown.append(row)
                    if category == "project_path":
                        project_paths.append(row)
    categories: dict[str, int] = {}
    for row in rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1
    return {
        "n_paths": len(rows),
        "n_files": len({row["file"] for row in rows}),
        "categories": categories,
        "unknown": unknown,
        "project_paths": project_paths,
        "rows": rows,
        "ok": not unknown and not project_paths,
    }


def count_bytecode() -> dict:
    pycache_dirs = []
    pyc_files = []
    for dirname in CODE_DIRS:
        root = ROOT / dirname
        if not root.exists():
            continue
        pycache_dirs.extend(sorted(root.rglob("__pycache__")))
        pyc_files.extend(sorted(root.rglob("*.pyc")))
    return {
        "pycache_dirs": [rel(p) for p in pycache_dirs],
        "pyc_files": [rel(p) for p in pyc_files],
        "n_pycache_dirs": len(pycache_dirs),
        "n_pyc_files": len(pyc_files),
        "ok": len(pycache_dirs) == 0 and len(pyc_files) == 0,
    }


def check_help_entries(python_exe: str) -> dict:
    results = []
    for script in HELP_SCRIPTS:
        path = ROOT / script
        if not path.exists():
            results.append({"script": script, "ok": False, "reason": "missing"})
            continue
        result = run_command([python_exe, script, "--help"], timeout=60)
        results.append({"script": script, **result})
    return {"results": results, "ok": all(r.get("ok") for r in results)}


def discover_argparse_scripts() -> list[str]:
    scripts = []
    root = ROOT / "scripts"
    if not root.exists():
        return scripts
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "argparse" not in text:
            continue
        if 'if __name__ == "__main__"' not in text and "if __name__ == '__main__'" not in text:
            continue
        scripts.append(rel(path))
    return scripts


def check_deep_help_entries(python_exe: str, timeout: int, enabled: bool) -> dict:
    scripts = discover_argparse_scripts()
    if not enabled:
        return {"enabled": False, "n_scripts": len(scripts), "results": [], "ok": True}

    results = []
    for script in scripts:
        result = run_command([python_exe, script, "--help"], timeout=timeout)
        results.append({"script": script, **result})
    return {"enabled": True, "n_scripts": len(scripts), "results": results, "ok": all(r.get("ok") for r in results)}


def check_utils_io_smoke(python_exe: str) -> dict:
    code = r"""
from pathlib import Path
import os
import tempfile
import numpy as np
import SimpleITK as sitk
from utils.io import write_like

with tempfile.TemporaryDirectory() as td:
    ref = sitk.GetImageFromArray(np.zeros((2, 3, 4), dtype=np.uint8))
    cwd = Path.cwd()
    os.chdir(td)
    try:
        write_like(np.ones((2, 3, 4), dtype=np.uint8), ref, "plain_name.nii.gz", dtype=np.uint8)
        assert Path("plain_name.nii.gz").exists()
    finally:
        os.chdir(cwd)
print("OK")
"""
    return run_command([python_exe, "-c", code], timeout=60)


def check_model_smoke(python_exe: str) -> dict:
    code = r"""
import torch
from models.factory import create_model

for name, kwargs in [
    ("unet3d", {"in_channels": 1, "out_channels": 1, "base_filters": 4}),
    ("sdf_refine_unet", {"in_channels": 2, "out_channels": 1, "base_filters": 4}),
]:
    model = create_model(name, **kwargs).eval()
    x = torch.zeros((1, kwargs["in_channels"], 8, 16, 16))
    with torch.no_grad():
        y = model(x)
    assert tuple(y.shape) == (1, 1, 8, 16, 16), (name, tuple(y.shape))
print("OK")
"""
    return run_command([python_exe, "-c", code], timeout=120)


def check_core_logic_smoke(python_exe: str) -> dict:
    code = r"""
import numpy as np
import SimpleITK as sitk
from utils.geometry import (
    signed_distance, select_annotated_slices, sparse_sdf_propagation,
    sparse_sdf_zcap_propagation, anatomy_valid_region, keep_seed_connected,
    z_uncertainty, sparse_hu_likelihood, contact_likelihood_volume,
    corridor_likelihood_volume, graphcut_contact_refine,
    sparse_geodesic_probability,
)
from utils.connectivity import (
    sparse_seed_from_slices, ball_structure, estimate_sparse_volume,
    connectivity_valid_region, lung_surface_completion_prior,
)
from utils.metrics import dice_score, hd95_asd, surface_distances
from utils.io import resample_to_spacing

mask = np.zeros((5, 7, 7), dtype=bool)
mask[1, 2:5, 2:5] = True
mask[3, 1:6, 1:6] = True
label = np.zeros(mask.shape, dtype=np.int16)
label[:, 1:6, 1:6] = 1
label[:, 3, 3] = 2
image = np.zeros(mask.shape, dtype=np.float32)

assert signed_distance(mask[1]).shape == mask[1].shape
assert set(select_annotated_slices(mask, 2, mode="even").tolist()).issubset({1, 3})
assert sparse_sdf_propagation(mask, [1, 3]).shape == mask.shape
assert sparse_sdf_zcap_propagation(mask, [1, 3], plateau=1, cap_len=2).shape == mask.shape
assert anatomy_valid_region(label, avoid_labels=(2,), lung_radius=2).shape == mask.shape
seed = sparse_seed_from_slices(mask, [1, 3])
assert seed[1].sum() == mask[1].sum()
assert ball_structure(1).shape == (3, 3, 3)
assert estimate_sparse_volume(mask, [1, 3]) >= mask[[1, 3]].sum()
assert connectivity_valid_region(label, seed, avoid_labels=(2,), lung_radius=2)[seed].all()
keep = np.zeros((3, 5, 5), dtype=bool)
keep[:, 1, 1] = True
keep[:, 4, 4] = True
seed2 = np.zeros_like(keep)
seed2[:, 1, 1] = True
assert not keep_seed_connected(keep, seed2)[:, 4, 4].any()
assert z_uncertainty(mask.shape, [1, 3], max_distance=2).shape == mask.shape
assert sparse_hu_likelihood(image, mask, [1, 3]).shape == mask.shape
assert contact_likelihood_volume(label, mask, [1, 3], organ_labels=(1, 2))[0].shape == mask.shape
assert corridor_likelihood_volume(image, label, mask, [1, 3], lung_label=1, oar_labels=(2,)).shape == mask.shape
assert lung_surface_completion_prior(image, label, mask, [1, 3], lung_label=1, avoid_labels=(2,))[0].shape == mask.shape
assert sparse_geodesic_probability(image, label, mask, [1, 3], iterations=1)[0].shape == mask.shape
assert graphcut_contact_refine(image, label, mask, mask, [1, 3], valid_region=np.ones_like(mask), solver="iterative", iterations=2)[0].shape == mask.shape

for fn, args in [
    (sparse_sdf_propagation, (mask, [])),
    (sparse_sdf_zcap_propagation, (mask, [])),
    (z_uncertainty, (mask.shape, [])),
    (contact_likelihood_volume, (label, mask, [])),
    (sparse_geodesic_probability, (image, label, mask, [])),
    (graphcut_contact_refine, (image, label, mask, mask, [])),
]:
    try:
        fn(*args)
    except ValueError as exc:
        assert "annotated_z" in str(exc)
    else:
        raise AssertionError(f"{fn.__name__} accepted empty annotated_z")

assert np.isclose(dice_score(mask, mask), 1.0)
assert np.isclose(dice_score(np.zeros_like(mask), np.zeros_like(mask)), 1.0)
assert surface_distances(mask, mask) is not None
assert hd95_asd(mask, mask) == (0.0, 0.0)
sitk_image = sitk.GetImageFromArray(np.zeros((2, 4, 6), dtype=np.float32))
sitk_image.SetSpacing((2, 2, 2))
assert resample_to_spacing(sitk_image, spacing=(1, 1, 1)).GetSize() == (12, 8, 4)
print("OK")
"""
    return run_command([python_exe, "-c", code], timeout=120)


def check_artifacts() -> dict:
    rows = []
    for artifact in REQUIRED_ARTIFACTS:
        path = ROOT / artifact
        row = {"path": artifact, "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}
        if path.suffix == ".zip" and path.exists():
            with zipfile.ZipFile(path) as zf:
                row["zip_bad_member"] = zf.testzip()
                row["zip_n_files"] = len(zf.namelist())
        if path.suffix == ".docx" and path.exists():
            with zipfile.ZipFile(path) as zf:
                row["zip_bad_member"] = zf.testzip()
                row["zip_n_files"] = len(zf.namelist())
        rows.append(row)
    return {"artifacts": rows, "ok": all(r["exists"] and not r.get("zip_bad_member") for r in rows)}


def check_current_results() -> dict:
    result_root = ROOT / "reports/best_ctv_method_vs_best_baseline_20260603"
    if not result_root.exists():
        return {
            "ok": True,
            "available": False,
            "reason": "optional generated result directory is absent; skipping local result consistency checks",
        }
    per_case = result_root / "per_case_dice_comparison.csv"
    slice_csv = result_root / "slice_dice_comparison.csv"
    manifest = result_root / "manifest.csv"
    summary = result_root / "summary.json"
    out = {"ok": True, "consistency_failures": []}
    if per_case.exists():
        out["per_case_lines"] = sum(1 for _ in per_case.open())
        out["per_case_data_rows"] = max(out["per_case_lines"] - 1, 0)
        with per_case.open(newline="") as f:
            per_case_rows = list(csv.DictReader(f))
    else:
        out["ok"] = False
        out["per_case_missing"] = True
        per_case_rows = []
    if slice_csv.exists():
        out["slice_lines"] = sum(1 for _ in slice_csv.open())
        out["slice_data_rows"] = max(out["slice_lines"] - 1, 0)
    else:
        out["ok"] = False
        out["slice_csv_missing"] = True
    if manifest.exists():
        with manifest.open(newline="") as f:
            manifest_rows = list(csv.DictReader(f))
        out["manifest_data_rows"] = len(manifest_rows)
    else:
        out["ok"] = False
        out["manifest_missing"] = True
        manifest_rows = []
    if summary.exists():
        data = json.loads(summary.read_text())
        out["summary"] = {
            "n": data.get("n"),
            "baseline_mean": data.get("baseline_mean"),
            "ours_mean": data.get("ours_mean"),
            "improved": data.get("improved"),
            "worse": data.get("worse"),
        }
    else:
        out["ok"] = False
        out["summary_missing"] = True
        data = {}
    if out.get("per_case_data_rows") != 31:
        out["ok"] = False
    if out.get("slice_data_rows") != 5165:
        out["ok"] = False
    if manifest_rows and per_case_rows and manifest_rows != per_case_rows:
        out["consistency_failures"].append("manifest.csv does not match per_case_dice_comparison.csv")

    if per_case_rows:
        baseline = [float(row["baseline_dice"]) for row in per_case_rows]
        ours = [float(row["ours_dice"]) for row in per_case_rows]
        delta = [float(row["delta_dice"]) for row in per_case_rows]
        n_slices = [int(row["n_slices"]) for row in per_case_rows]
        selected_z_counts = [len([z for z in row["selected_z"].split(";") if z != ""]) for row in per_case_rows]
        mismatch = [float(row.get("baseline_regen_mismatch_fraction", "0") or 0) for row in per_case_rows]

        def mean(values: list[float]) -> float:
            return sum(values) / max(len(values), 1)

        def std(values: list[float]) -> float:
            avg = mean(values)
            return math.sqrt(sum((v - avg) ** 2 for v in values) / max(len(values), 1))

        computed = {
            "n": len(per_case_rows),
            "baseline_mean": mean(baseline),
            "baseline_std": std(baseline),
            "ours_mean": mean(ours),
            "ours_std": std(ours),
            "delta_mean": mean(delta),
            "delta_std": std(delta),
            "improved": sum(1 for v in delta if v > 0),
            "worse": sum(1 for v in delta if v < 0),
            "n_slices_sum": sum(n_slices),
            "max_baseline_regen_mismatch_fraction": max(mismatch) if mismatch else 0.0,
        }
        out["computed_from_per_case"] = computed

        for key in ("n", "improved", "worse"):
            if data.get(key) != computed[key]:
                out["consistency_failures"].append(f"summary {key} != per-case computed {key}")
        for key in ("baseline_mean", "baseline_std", "ours_mean", "ours_std", "delta_mean", "delta_std"):
            if abs(float(data.get(key, float("nan"))) - computed[key]) > 1e-12:
                out["consistency_failures"].append(f"summary {key} != per-case computed {key}")
        if abs(computed["delta_mean"] - (computed["ours_mean"] - computed["baseline_mean"])) > 1e-12:
            out["consistency_failures"].append("delta_mean is inconsistent with ours_mean - baseline_mean")
        if any(count != 7 for count in selected_z_counts):
            out["consistency_failures"].append("not every case has exactly 7 selected sparse prompt slices")
        if computed["max_baseline_regen_mismatch_fraction"] > 1e-12:
            out["consistency_failures"].append("baseline regeneration mismatch is nonzero")
        if out.get("slice_data_rows") is not None and out["slice_data_rows"] != computed["n_slices_sum"]:
            out["consistency_failures"].append("slice CSV rows do not match summed n_slices")

        missing_case_paths = []
        for row in per_case_rows:
            for key in ("ct_path", "gt_path", "baseline_nii", "ours_nii", "prompt_nii"):
                path = ROOT / row[key]
                if not path.exists():
                    missing_case_paths.append({"case": row["case"], "key": key, "path": row[key]})
        out["missing_case_paths"] = missing_case_paths[:20]
        if missing_case_paths:
            out["consistency_failures"].append(f"{len(missing_case_paths)} per-case referenced paths are missing")

    nii_counts = {}
    for dirname in (
        "baseline_linear_mask_interpolation_k7",
        "ours_train_calibrated_support_intersection_rule",
        "sparse_prompt_k7_even_nonempty",
    ):
        path = result_root / "nii" / dirname
        nii_counts[dirname] = len(list(path.glob("*.nii.gz"))) if path.exists() else 0
    out["nii_counts"] = nii_counts
    if any(count != 31 for count in nii_counts.values()):
        out["consistency_failures"].append("NIfTI output counts are not 31 in every expected directory")

    png_count = len(list((result_root / "slices").glob("*/*.png"))) if (result_root / "slices").exists() else 0
    out["slice_png_count"] = png_count
    if out.get("slice_data_rows") is not None and png_count != out["slice_data_rows"]:
        out["consistency_failures"].append("slice PNG count does not match slice CSV rows")

    if out["consistency_failures"]:
        out["ok"] = False
    return out


def check_export_workflow_smoke(python_exe: str, enabled: bool) -> dict:
    if not enabled:
        return {"enabled": False, "ok": True}

    smoke_parent = ROOT / "reports"
    smoke_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ctv_export_smoke_", dir=str(smoke_parent)) as temp_dir:
        out_dir = Path(temp_dir) / "best_method_export_smoke"
        result = run_command(
            [
                python_exe,
                "scripts/export_best_ctv_method_vs_baseline_html.py",
                "--out_dir",
                str(out_dir),
                "--max_cases",
                "1",
                "--skip_existing_slices",
                "--skip_slice_pngs",
                "--skip_html",
                "--use_existing_masks",
                "--skip_nifti_write",
            ],
            timeout=180,
        )
        out = {"enabled": True, "command": result, "out_dir_removed_after_check": True, "ok": result["ok"], "failures": []}
        if not result["ok"]:
            return out

        required = [
            out_dir / "per_case_dice_comparison.csv",
            out_dir / "slice_dice_comparison.csv",
            out_dir / "manifest.csv",
            out_dir / "summary.json",
        ]
        missing = [str(path.relative_to(out_dir)) for path in required if not path.exists()]
        if missing:
            out["failures"].append({"missing_required_outputs": missing})

        with (out_dir / "summary.json").open() as f:
            summary = json.load(f)
        with (out_dir / "per_case_dice_comparison.csv").open(newline="") as f:
            per_case_rows = list(csv.DictReader(f))
        with (out_dir / "manifest.csv").open(newline="") as f:
            manifest_rows = list(csv.DictReader(f))
        with (out_dir / "slice_dice_comparison.csv").open(newline="") as f:
            slice_rows = list(csv.DictReader(f))

        out["summary"] = {
            "n": summary.get("n"),
            "baseline_mean": summary.get("baseline_mean"),
            "ours_mean": summary.get("ours_mean"),
            "delta_mean": summary.get("delta_mean"),
        }
        out["per_case_rows"] = len(per_case_rows)
        out["slice_rows"] = len(slice_rows)
        if summary.get("n") != 1 or len(per_case_rows) != 1 or len(manifest_rows) != 1:
            out["failures"].append("expected exactly one per-case/manifest row")
        if per_case_rows != manifest_rows:
            out["failures"].append("smoke manifest does not match per-case CSV")

        if per_case_rows:
            row = per_case_rows[0]
            case = row["case"]
            n_slices = int(row["n_slices"])
            selected_z_count = len([z for z in row["selected_z"].split(";") if z])
            if selected_z_count != 7:
                out["failures"].append("smoke case does not have 7 selected prompt slices")
            if len(slice_rows) != n_slices:
                out["failures"].append("smoke slice rows do not match case n_slices")
            for key in ("baseline_nii", "ours_nii", "prompt_nii"):
                path = ROOT / row[key]
                if not path.exists():
                    out["failures"].append(f"smoke referenced NIfTI missing: {row[key]}")

            for key in ("baseline_dice", "ours_dice", "delta_dice"):
                if not math.isfinite(float(row[key])):
                    out["failures"].append(f"smoke non-finite {key}")

        referenced_nii_count = 0
        if per_case_rows:
            row = per_case_rows[0]
            referenced_nii_count = sum(1 for key in ("baseline_nii", "ours_nii", "prompt_nii") if (ROOT / row[key]).exists())
        out["referenced_nii_count"] = referenced_nii_count
        if referenced_nii_count != 3:
            out["failures"].append("smoke did not reference three existing NIfTI masks")

        output_nii_counts = {}
        for dirname in (
            "baseline_linear_mask_interpolation_k7",
            "ours_train_calibrated_support_intersection_rule",
            "sparse_prompt_k7_even_nonempty",
        ):
            output_nii_counts[dirname] = len(list((out_dir / "nii" / dirname).glob("*.nii.gz")))
        out["output_nii_counts"] = output_nii_counts
        if any(count != 0 for count in output_nii_counts.values()):
            out["failures"].append("fast smoke should not write temporary NIfTI masks")

        png_count = len(list((out_dir / "slices").glob("*/*.png")))
        out["slice_png_count"] = png_count
        if png_count != 0:
            out["failures"].append("fast smoke should not render slice PNGs")

        out["ok"] = not out["failures"]
        return out


def make_report(args: argparse.Namespace) -> dict:
    python_exe = str(args.python)
    script_inventory = check_script_inventory()
    report = {
        "root": str(ROOT),
        "python": python_exe,
        "checks": {
            "python_syntax": check_python_syntax(),
            "unused_imports": check_unused_imports(),
            "shell_syntax": check_shell_syntax(),
            "shell_references": check_shell_references(),
            "script_inventory": script_inventory,
            "script_main_guards": check_script_main_guards(),
            "historical_archive_manifest": check_historical_archive_manifest(script_inventory),
            "absolute_path_dependencies": check_absolute_path_dependencies(),
            "bytecode": count_bytecode(),
            "help_entries": check_help_entries(python_exe),
            "deep_help_entries": check_deep_help_entries(python_exe, args.help_timeout, args.deep_entrypoints),
            "utils_io_smoke": check_utils_io_smoke(python_exe),
            "core_logic_smoke": check_core_logic_smoke(python_exe),
            "model_smoke": check_model_smoke(python_exe),
            "artifacts": check_artifacts(),
            "current_results": check_current_results(),
            "export_workflow_smoke": check_export_workflow_smoke(python_exe, args.workflow_smoke),
        },
    }
    report["ok"] = all(check.get("ok") for check in report["checks"].values())
    return report


def write_script_inventory(report: dict, out_path: Path) -> None:
    rows = report["checks"]["script_inventory"]["rows"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "type", "category", "role"])
        writer.writeheader()
        writer.writerows(rows)


def write_absolute_path_manifest(report: dict, out_path: Path) -> None:
    rows = report["checks"]["absolute_path_dependencies"]["rows"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "line", "path", "category", "context"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    default_python = str(DEFAULT_UMAMBA_PYTHON if DEFAULT_UMAMBA_PYTHON.exists() else Path(sys.executable))
    parser = argparse.ArgumentParser(description="Audit project-owned code without running expensive experiments.")
    parser.add_argument("--python", default=default_python, help="Python executable used for import/smoke checks.")
    parser.add_argument("--out_json", default=str(ROOT / "reports/code_audit_latest.json"))
    parser.add_argument("--out_inventory", default=str(ROOT / "reports/script_inventory_latest.csv"))
    parser.add_argument("--out_abs_paths", default=str(ROOT / "reports/absolute_path_dependency_manifest.csv"))
    parser.add_argument("--deep_entrypoints", action="store_true", help="Run --help for every argparse script in scripts/.")
    parser.add_argument("--workflow_smoke", action="store_true", help="Run a heavier one-case best-method export smoke test.")
    parser.add_argument("--help_timeout", type=int, default=20, help="Per-script timeout for deep entrypoint --help checks.")
    args = parser.parse_args()

    report = make_report(args)
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    inventory_path = Path(args.out_inventory)
    write_script_inventory(report, inventory_path)
    abs_paths_path = Path(args.out_abs_paths)
    write_absolute_path_manifest(report, abs_paths_path)

    print(f"Wrote {out_path}")
    print(f"Wrote {inventory_path}")
    print(f"Wrote {abs_paths_path}")
    print(f"Overall OK: {report['ok']}")
    for name, check in report["checks"].items():
        print(f"{name}: {'OK' if check.get('ok') else 'FAIL'}")
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
