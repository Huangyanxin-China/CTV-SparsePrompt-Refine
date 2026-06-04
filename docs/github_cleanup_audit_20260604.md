# GitHub cleanup and logic audit

Date: 2026-06-04

## Scope

This audit reviews the current `CTV_SparsePrompt_Refine` workspace for:

- unnecessary local files that should not be part of a public code repository;
- runnable-but-wrong logic risks in the current method scripts and manuscript;
- repository structure needed for a future GitHub upload.

## Cleanup performed

Removed from the workspace:

- `failed_experiments_overleaf/`
  - old failed-experiment Overleaf package, no longer part of the current manuscript.
- `manuscript_vsi_biomedical_data/`
  - earlier VSI manuscript package superseded by
    `manuscript_pr_biomedical_data_refine_20260603/`.
- `cover letter.docx`
  - old top-level submission file, not code or current manuscript source.
- invalid empty `.git/`
  - replaced by a fresh `git init` so `.gitignore` and `git status` can be checked.
- project-owned Python bytecode caches under `scripts/`, `models/`, `utils/`, and
  `python_compat/`.
- patient/date-bearing figure filenames in the current manuscript package were
  renamed to generic example names.
- the private-case figure manifest under the current manuscript figure folder
  was removed because the manuscript figures themselves are sufficient.

Retained but ignored for GitHub:

- private data: `data/`, `dcm/`, `nnunet_runs/`;
- model checkpoints and external run folders: `checkpoints/`, `external_runs/`,
  `external_runs_umamba_bs1/`;
- large generated results: `results/`, `logs/`, full-slice HTML assets, NIfTI
  predictions, and transfer packages;
- local agent/cockpit state: `.agents/`, `.codex/`, `research_cockpit/`;
- controlled/public data mirrors: `public_data/`;
- GTV/CTV package NIfTI exports, generated outputs, resources, and package
  manifest.
- `reports/` as a whole, because it is treated as a local generated-results
  directory and may contain per-case identifiers or large visualization assets.
- local historical/private experiment traces under `scripts/archive/`.

## Repository files added or updated

- Added root `README.md` describing the current method, workflow, entry points,
  data privacy boundary, and code map.
- Added `.gitignore` to keep private data, large results, checkpoints, caches,
  and manuscript build artifacts out of version control.
- Updated `scripts/audit_project_code.py`:
  - added current refine-network and visualization scripts to the script
    inventory classification;
  - changed required artifacts to repository-contained source files and
    representative manuscript figures;
  - made generated-result consistency checks optional when `reports/` is absent
    in a public clone;
  - kept the audit non-training and non-download by default.
- Added `docs/historical_experiment_archive_manifest.csv` so archived
  historical scripts have explicit retention decisions.
- Updated `manuscript_pr_biomedical_data_refine_20260603/README.md` to use
  XeLaTeX instead of pdfLaTeX.
- Updated `manuscript_pr_biomedical_data_refine_20260603/main.tex` to align
  OAR claims with the actual implementation.

## Logic findings

### Finding 1: OAR role needed clearer separation

The K=7 preprocessing screen scripts:

- `scripts/run_k7_preprocess_variant_screen.py`
- `scripts/run_data_preprocess_chooser_k7.py`

generate their deployable pseudo-label candidates from sparse prompts, SDF
support, and linear/core intersections. In those scripts, OAR is passed as a
zero mask for the geometric pseudo-label screen. Therefore the reported
support-intersection pseudo-label Dice should not be described as an OAR-driven
gain.

The supervised refine network:

- `scripts/train_ctv_pseudo_refine_net.py`

does use OAR information through:

- `anatomy_roi_from_oar(...)`;
- spinal-cord exclusion;
- OAR-derived ROI and context channels;
- final probability masking inside the envelope/prompt-constrained candidate
  region.

Resolution:

- The manuscript was revised to describe the pseudo-label score as the geometric
  SDF/support-intersection output.
- The OAR contribution is now described as an anatomical ROI/context constraint
  for the downstream refine network, not as the sole source of pseudo-label
  improvement.

### Finding 2: Test labels are used for simulation and evaluation, not rule tuning

The sparse-prompt experiments use complete CTV labels from test cases to
simulate sparse prompt slices and to compute final metrics. This is acceptable
for retrospective prompt simulation, provided the complete test label is not
used to tune thresholds or select methods.

Checked scripts:

- `scripts/run_k7_preprocess_variant_screen.py`
  - fixed and threshold rules are calibrated only from training rows;
  - test rows are evaluated after the train-calibrated rule is fixed.
- `scripts/run_data_preprocess_chooser_k7.py`
  - chooser threshold is calibrated from training features and training Dice;
  - test rows are evaluated after calibration.
- `scripts/train_ctv_pseudo_refine_net.py`
  - checkpoint and threshold selection use an internal validation split;
  - test labels are used only for final metrics.

Remaining caution:

- Visualization scripts may choose representative slices using GT area; this is
  acceptable for qualitative figures but should not be described as deployment
  inference.

### Finding 3: SAM-Med3D oracle outputs must remain diagnostic

The OAR and CTV visualization/report scripts include SAM-Med3D oracle columns
where prompts are derived from full GT. These should remain clearly labeled as
diagnostic, not fair deployable baselines.

Current manuscript and figure captions now state this distinction.

## Automated audit result

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/audit_project_code.py \
  --out_json reports/github_cleanup_audit_after_fixes_20260604.json \
  --out_inventory reports/github_cleanup_script_inventory_after_fixes_20260604.csv \
  --out_abs_paths reports/github_cleanup_absolute_paths_after_fixes_20260604.csv
```

Result:

```text
Overall OK: True
python_syntax: OK
unused_imports: OK
shell_syntax: OK
shell_references: OK
script_inventory: OK
script_main_guards: OK
historical_archive_manifest: OK
absolute_path_dependencies: OK
bytecode: OK
help_entries: OK
deep_help_entries: OK
utils_io_smoke: OK
core_logic_smoke: OK
model_smoke: OK
artifacts: OK
current_results: OK
export_workflow_smoke: OK
```

The final rerun after privacy-oriented filename cleanup also passed and was
written locally to:

```text
reports/github_cleanup_audit_final_20260604.json
reports/github_cleanup_script_inventory_final_20260604.csv
reports/github_cleanup_absolute_paths_final_20260604.csv
```

These `reports/` files remain local generated audit evidence and are ignored by
Git.

## Current GitHub-ready structure

Recommended files/directories to include:

- `.gitignore`
- `README.md`
- `docs/`
- `scripts/`
- `models/`
- `utils/`
- `python_compat/`
- `manuscript_pr_biomedical_data_refine_20260603/`
- `docs/method_implementation_code_locations_20260604.md`
- `gtv_ctv_repro_package_20260604/` code and README only

Recommended files/directories to keep local and not upload:

- private clinical data and DICOM/NIfTI files;
- nnUNet raw/preprocessed/result folders;
- checkpoints and external run outputs;
- full-slice HTML assets and per-case clinical overlays;
- generated transfer zips/tarballs;
- local agent skills and cockpit state.

Privacy-oriented candidate scan:

```bash
git ls-files --others --exclude-standard -z \
  | xargs -0 grep -nE 'P[0-9]{5,}|CT20[0-9]{6}'
```

Result after cleanup: no matches in files that Git would currently consider for
upload.

## Current repository status

A fresh `.git/` was initialized only to validate ignore behavior. No commit has
been made.

Use:

```bash
git status --short --ignored
```

to inspect upload candidates before the first commit.
