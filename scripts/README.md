# Scripts Guide

This directory contains the public, data-agnostic entry points for the
CTV sparse-prompt refinement workflow. Commands require explicit local input
paths because private datasets are not included in this repository.

## Preprocessing

Sparse-prompt SDF/core-envelope workflow:

```bash
python scripts/run_sparse_prompt_core_envelope_workflow.py \
  --ct_dir /path/to/local_dataset/imagesTs \
  --gt_dir /path/to/local_dataset/labelsTs \
  --oar_dir /path/to/local_oar_dataset/labelsTs \
  --out_root results/demo_sparse_prompt_workflow
```

K=7 support-intersection screening:

```bash
python scripts/run_k7_preprocess_variant_screen.py \
  --train_label_dir /path/to/local_dataset/labelsTr \
  --test_label_dir /path/to/local_dataset/labelsTs \
  --out_dir results/demo_k7_screen
```

Train-calibrated data-preprocessing chooser:

```bash
python scripts/run_data_preprocess_chooser_k7.py \
  --train_label_dir /path/to/local_dataset/labelsTr \
  --test_label_dir /path/to/local_dataset/labelsTs \
  --out_dir results/demo_preprocess_chooser
```

Traditional sparse-slice interpolation baseline:

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
  --out_dir results/demo_refine_train
```

Use precomputed pseudo-labels:

```bash
python scripts/train_ctv_pseudo_refine_net.py \
  --source /path/to/local_dataset \
  --oar_source /path/to/local_oar_dataset \
  --feature_source precomputed \
  --pseudo_train_dir /path/to/local_pseudo/labelsTr \
  --pseudo_test_dir /path/to/local_pseudo/labelsTs \
  --rule_json /path/to/local_rule/summary.json \
  --out_dir results/demo_refine_train
```

## Evaluation

Folder-level segmentation metrics:

```bash
python scripts/evaluate_segmentation_folder.py \
  --pred_dir /path/to/predictions \
  --gt_dir /path/to/local_dataset/labelsTs \
  --out_csv results/demo_eval/per_case_metrics.csv
```

Dice-only evaluation:

```bash
python scripts/evaluate_segmentation_dice_only.py \
  --pred_dir /path/to/predictions \
  --gt_dir /path/to/local_dataset/labelsTs
```

## Privacy Notes

- Do not hard-code private data roots into committed scripts.
- Do not commit generated `results/`, predictions, checkpoints, logs, or
  medical-image volumes.
- Use `docs/privacy_release_checklist.md` before public pushes.
