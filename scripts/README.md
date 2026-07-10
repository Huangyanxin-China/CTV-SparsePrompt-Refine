# Scripts Guide

This directory contains the public, data-agnostic entry points for the CTV
sparse-prompt refinement workflow. Commands require explicit local input paths
because private datasets are not included.

Read `docs/DATA_FORMAT.md` before running a new dataset. Aligned medical images
must share size, spacing, origin, and direction.

## Preprocessing

Run SDF/core-envelope configuration screening on development data:

```bash
python scripts/run_sparse_prompt_core_envelope_workflow.py \
  --ct_dir /path/to/development/images \
  --gt_dir /path/to/development/labels \
  --oar_dir /path/to/development/oar_labels \
  --target_label 1 \
  --spinal_label 3 \
  --out_root results/demo_sparse_prompt_workflow
```

This command includes a GT-derived oracle diagnostic. Do not use its ranking to
select a configuration on the held-out test set.

Calibrate a K=7 support-intersection rule on training labels and evaluate the
frozen rule once on held-out labels:

```bash
python scripts/run_k7_preprocess_variant_screen.py \
  --train_label_dir /path/to/local_dataset/labelsTr \
  --test_label_dir /path/to/local_dataset/labelsTs \
  --out_dir results/demo_k7_screen
```

The output includes both `summary.json` and a directly consumable
`selected_threshold_rule.json`.

A restricted two-method chooser remains available:

```bash
python scripts/run_data_preprocess_chooser_k7.py \
  --train_label_dir /path/to/local_dataset/labelsTr \
  --test_label_dir /path/to/local_dataset/labelsTs \
  --out_dir results/demo_preprocess_chooser
```

Run the traditional interpolation baseline from pre-generated sparse prompts:

```bash
python scripts/run_traditional_linear_mask_interpolation_baseline.py \
  --gt_dir /path/to/local_dataset/labelsTs \
  --prompt_dir /path/to/local_sparse_prompts \
  --out_dir results/demo_linear_interpolation \
  --write_predictions
```

## Refinement Network

Generate features on the fly:

```bash
python scripts/train_ctv_pseudo_refine_net.py \
  --source /path/to/local_dataset \
  --oar_source /path/to/local_oar_dataset \
  --feature_source generate \
  --target_label 1 \
  --spinal_label 3 \
  --subject_separator _CT \
  --out_dir results/demo_refine_train
```

`--subject_separator` groups repeated scans such as `P001_CT1` and
`P001_CT2` so that one subject cannot cross the train/validation boundary.

Use precomputed pseudo-labels:

```bash
python scripts/train_ctv_pseudo_refine_net.py \
  --source /path/to/local_dataset \
  --oar_source /path/to/local_oar_dataset \
  --feature_source precomputed \
  --pseudo_train_dir /path/to/local_pseudo/labelsTr \
  --pseudo_test_dir /path/to/local_pseudo/labelsTs \
  --rule_json results/demo_k7_screen/selected_threshold_rule.json \
  --out_dir results/demo_refine_train
```

An explicitly supplied missing or malformed rule file fails instead of silently
falling back to an embedded rule.

## Evaluation

Strict folder-level Dice and surface metrics:

```bash
python scripts/evaluate_segmentation_folder.py \
  --pred_dir /path/to/predictions \
  --gt_dir /path/to/local_dataset/labelsTs \
  --classes 1 \
  --class_names CTV \
  --output_csv results/demo_eval/per_case_metrics.csv \
  --output_json results/demo_eval/summary.json
```

Strict Dice-only evaluation:

```bash
python scripts/evaluate_segmentation_dice_only.py \
  --pred_dir /path/to/predictions \
  --gt_dir /path/to/local_dataset/labelsTs \
  --classes 1 \
  --class_names CTV \
  --output_csv results/demo_eval/per_case_dice.csv \
  --output_json results/demo_eval/dice_summary.json
```

Both evaluators enumerate the GT manifest. Missing predictions and physical
geometry mismatches fail by default. `--allow_missing` and
`--skip_invalid_geometry` are debug-only escape hatches and must be disclosed
if used.

## Verification

```bash
python -m compileall -q models scripts utils tests
ruff check models scripts utils tests
pytest -q
```

Tests use synthetic data only.

## Privacy Notes

- Do not hard-code private data roots into committed scripts.
- Do not commit generated results, predictions, checkpoints, logs, or
  medical-image volumes.
- Use `docs/privacy_release_checklist.md` before public pushes.
- Report accidental data exposure through the private process in
  `SECURITY.md`, not a public issue.
