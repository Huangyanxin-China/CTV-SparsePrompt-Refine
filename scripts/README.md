# Scripts Guide

This directory contains both stable workflow scripts and historical experiment
scripts. Use the sections below as the current source of truth for the
canonical commands.

## Code Audit

Run this before packaging or after editing project code:

```bash
PYTHONDONTWRITEBYTECODE=1 \
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/audit_project_code.py
```

The audit checks project-owned Python and shell syntax, selected command entry
points, shell-script references, Python script `__main__` guards, current
result artifacts, Word/TeX report integrity, and lightweight
model/util/core-logic smoke tests. It does not start training, downloads, or
full-cohort inference.

For a broader but slower check of every argparse-based Python entry point:

```bash
PYTHONDONTWRITEBYTECODE=1 \
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/audit_project_code.py --deep_entrypoints
```

For a one-case export workflow smoke test:

```bash
PYTHONDONTWRITEBYTECODE=1 \
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/audit_project_code.py --workflow_smoke
```

This writes to a temporary `reports/.ctv_export_smoke_*` directory and removes
it after the check. The smoke test uses a small case and skips PNG/HTML
rendering. It also reuses the existing best-method masks and skips temporary
NIfTI writing, so it validates CSV/summary generation and referenced-mask
consistency without repeating slow full-volume SDF candidate regeneration,
compressed NIfTI writing, or all-slice overlay rendering.

Machine-readable output:

```text
reports/code_audit_latest.json
reports/script_inventory_latest.csv
reports/historical_experiment_archive_manifest.csv
reports/absolute_path_dependency_manifest.csv
```

The script inventory classifies every top-level Python and shell script under
`scripts/`. The current categories are:

```text
current_method
baseline_segmentation
data_preparation
report_generation
historical_experiment
submission_vsi
maintenance
utility
```

Historical experiment scripts are retained for provenance and tracked in
`reports/historical_experiment_archive_manifest.csv`. The audit verifies that
every script classified as `historical_experiment` appears in that manifest.

Absolute path dependencies are retained in
`reports/absolute_path_dependency_manifest.csv`. The audit classifies known
Python environments, external repos, nnU-Net datasets, external data inputs,
and local raw-data paths so hard-coded machine dependencies remain visible.
Project-root paths in project-owned source should be inferred dynamically from
the script location. Reintroducing a hard-coded project root or an unknown
absolute path fails the audit.

## Current Main CTV Sparse-Prompt Method

These are the current canonical scripts for the K=7 sparse-prompt CTV
preprocessing method.

### 1. Traditional Linear Interpolation Baseline

```bash
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/run_traditional_linear_mask_interpolation_baseline.py \
  --write_predictions
```

Main outputs:

```text
results/traditional_linear_mask_interpolation_k7/summary.json
results/traditional_linear_mask_interpolation_k7/per_case_metrics.csv
results/traditional_linear_mask_interpolation_k7/labels/
```

### 2. K=7 SDF Variant Screening and Support-Intersection Rule

```bash
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/run_k7_preprocess_variant_screen.py
```

Main outputs:

```text
results/data_preprocess_variant_screen_k7_20260602/summary.json
results/data_preprocess_variant_screen_k7_20260602/per_case_metrics.csv
results/data_preprocess_variant_screen_k7_20260602/test_metrics_with_surface.csv
```

Current deployable rule:

```text
rho = |C| / |Y_base|
theta = 0.990869732950405

if rho < theta:
    Y_ours = linear_core_intersection
else:
    Y_ours = support_100
```

### 3. Export Best Method vs Best Baseline

This exports per-case Dice, all-slice HTML overlays, and 3D NIfTI masks.

```bash
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/export_best_ctv_method_vs_baseline_html.py \
  --out_dir reports/best_ctv_method_vs_best_baseline_20260603
```

Main outputs:

```text
reports/best_ctv_method_vs_best_baseline_20260603/index.html
reports/best_ctv_method_vs_best_baseline_20260603/per_case_dice_comparison.csv
reports/best_ctv_method_vs_best_baseline_20260603/slice_dice_comparison.csv
reports/best_ctv_method_vs_best_baseline_20260603/nii/
```

## Method Documentation and Presentation

### Word Method Report

```bash
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/create_best_method_word_report.py
```

Outputs:

```text
reports/method_word/CTV_best_method_workflow_formula_schematic_20260603.docx
reports/method_word/best_method_detailed_schematic.png
```

### Overleaf TeX Project

```bash
python scripts/create_best_method_tex_project.py
```

Outputs:

```text
reports/method_tex/CTV_best_method_tex_project_20260603/
reports/method_tex/CTV_best_method_tex_project_20260603.zip
```

Use XeLaTeX on Overleaf.

### Stage-Results PPT

```bash
/share3/home/huangyanxin/miniconda3/envs/umamba/bin/python \
  scripts/create_stage_results_ppt.py
```

Output:

```text
reports/ppt/CTV_sparse_prompt_stage_results_20260602.pptx
```

## Baseline Segmentation Scripts

These scripts manage neural-network baselines and external methods. They may
start training/inference jobs and should be run deliberately on the intended
server/GPU environment.

```text
run_dataset014_oar_train_server05.sh
run_dataset015_ctv_train_server05.sh
run_external_seg_baselines_server05.sh
run_downstream_pseudo_ctv_nnunet_server05.sh
sammed3d_sparse_prompt_infer_dataset.py
sammed3d_nonoracle_infer_dataset.py
diffunet_train_dataset.py
diffunet_predict_dataset.py
```

## Historical / Exploratory Experiment Scripts

Historical and exploratory experiment scripts have been moved out of the
top-level script directory and archived under:

```text
scripts/archive/historical_experiments/
```

They are retained as experiment provenance, not as recommended entry points for
the current main result. The authoritative archive manifest is:

```text
reports/historical_experiment_archive_manifest.csv
```

The audit still checks archived historical scripts for syntax and missing shell
references, but only top-level scripts are treated as current operational entry
points.

## Submission / VSI Manuscript Utility Scripts

Scripts named `create_vsi_*`, `verify_vsi_*`, `sync_vsi_*`, and
`apply_vsi_*` are manuscript/submission packaging utilities. They are separate
from the CTV preprocessing method implementation.

## Cleanup Policy

- Do not delete historical experiment scripts without first archiving them with
  a manifest.
- Generated caches (`__pycache__/`, `*.pyc`) should not be kept.
- Heavy generated outputs should stay under `results/`, `reports/`,
  `external_runs/`, or `nnunet_runs/`, not mixed into `scripts/`.
- New canonical commands should be added to this README and included in
  `scripts/audit_project_code.py` when possible.
