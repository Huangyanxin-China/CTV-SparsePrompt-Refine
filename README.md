# CTV Sparse-Prompt Refinement

This repository contains code and lightweight manuscript artifacts for a
sparse-prompt clinical target volume (CTV) completion workflow.

The project is framed as medical data preprocessing for radiotherapy target
delineation: sparse 2D clinician prompts are converted into structured signed
distance field (SDF) priors, anatomical organ-at-risk (OAR) constraints define
the legal search region, and a constrained pseudo-to-true refinement model is
used to improve the generated CTV mask.

## Current Main Workflow

1. Build or load aligned planning CT, OAR masks, and expert CTV labels.
2. Simulate or receive sparse 2D CTV prompt slices.
3. Generate SDF-propagated pseudo targets and multi-candidate support maps.
4. Construct core-envelope priors under OAR constraints.
5. Select the deployable K=7 support-intersection preprocessing output.
6. Optionally train/evaluate the supervised pseudo-to-true refine network.
7. Evaluate against hidden complete CTV labels using Dice, HD95, ASD, volume
   error, prompt-slice Dice, and unseen-slice Dice.

## Key Entry Points

Install the core Python dependencies first:

```bash
pip install -r requirements.txt
```

Sparse-prompt preprocessing:

```bash
python scripts/run_sparse_prompt_core_envelope_workflow.py --help
python scripts/run_k7_preprocess_variant_screen.py --help
python scripts/run_data_preprocess_chooser_k7.py --help
```

Traditional interpolation baseline:

```bash
python scripts/run_traditional_linear_mask_interpolation_baseline.py --help
```

Supervised pseudo-to-true refinement:

```bash
python scripts/train_ctv_pseudo_refine_net.py --help
python scripts/evaluate_ctv_refine_safety_fusion.py --help
```

Visualization:

```bash
python scripts/create_ctv_html_visualization.py --help
python scripts/create_oar_html_visualization.py --help
python scripts/generate_pr_visual_figures.py --help
```

Static GitHub Pages showcase:

```bash
python -m http.server 8000 --directory site
```

GitHub repository and user-page deployment, after setting a GitHub token:

```bash
export GITHUB_TOKEN='YOUR_TOKEN_HERE'
bash scripts/deploy_to_github_pages.sh
unset GITHUB_TOKEN
```

Project audit:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/audit_project_code.py
```

## Repository Layout

- `scripts/`: canonical workflow, baseline, evaluation, visualization, and
  audit scripts.
- `models/`: lightweight 3D network modules used by the supervised refine
  experiment.
- `utils/`: reusable IO, metrics, geometry, and connectivity helpers.
- `docs/`: experiment plans and external-data notes.
- `site/`: lightweight anonymized project showcase for GitHub Pages or a
  personal user-page link.
- `manuscript_pr_biomedical_data_refine_20260603/`: current manuscript source,
  tables, and lightweight figures.
- `reports/`: lightweight result summaries and selected HTML/figure outputs.
- `scripts/archive/historical_experiments/`: retained exploratory scripts for
  provenance, not recommended as current entry points.

## Data and Privacy

Private clinical CT, OAR, CTV, GTV, DICOM, NIfTI, nnUNet caches, model
checkpoints, and generated prediction volumes are intentionally excluded from
Git tracking. The `.gitignore` keeps these local workspace artifacts out of the
public repository.

## Method-Code Map

For a detailed file-by-file implementation index, see:

```text
docs/method_implementation_code_locations_20260604.md
```

For deployment details, see:

```text
docs/github_deployment_20260604.md
```
