# Method Implementation Code Locations

This file records the code entry points for the current CTV sparse-prompt completion and supervised pseudo-to-true refinement workflow.

## Main Proposed Method

- Sparse-prompt SDF/core-envelope workflow:
  - `scripts/run_sparse_prompt_core_envelope_workflow.py`
  - `scripts/run_next_sparse_prompt_experiments_server05.sh`
  - `scripts/run_k7_preprocess_variant_screen.py`
  - `scripts/generate_sdf_pseudo_from_sparse_prompts.py`

- Train-calibrated support-intersection pseudo-label selection:
  - `scripts/run_data_preprocess_chooser_k7.py`
  - `scripts/summarize_k7_variant_surface.py`
  - results: `results/data_preprocess_variant_screen_k7_20260602/`
  - reports: `reports/data_preprocess_support_intersection_results.csv`
  - reports: `reports/ctv_main_experiment_results.csv`

- Supervised pseudo-to-true refine network:
  - `scripts/train_ctv_pseudo_refine_net.py`
  - `scripts/run_ctv_pseudo_refine_net_gpu1.sh`
  - `scripts/evaluate_ctv_refine_safety_fusion.py`
  - results: `results/ctv_pseudo_refine_net_k7_oarroi_fastmargin_supervised_gpu1/`
  - safety-fusion evaluation: `results/ctv_pseudo_refine_net_k7_oarroi_fastmargin_supervised_gpu1_safety_fusion_eval/`

## Baseline Segmentation and Evaluation

- Dataset creation:
  - `scripts/create_dataset004_oar_only.py`
  - `scripts/create_dataset004_ctv_only.py`
  - `scripts/create_one_case_train_dataset.py`

- nnU-Net OAR/CTV training:
  - `scripts/run_dataset014_oar_train_server05.sh`
  - `scripts/run_dataset015_ctv_train_server05.sh`
  - `scripts/run_nnunet_independent_test_server05.sh`

- External baselines:
  - `scripts/run_external_seg_baselines_server05.sh`
  - `scripts/diffunet_train_dataset.py`
  - `scripts/diffunet_predict_dataset.py`
  - `scripts/sammed3d_nonoracle_infer_dataset.py`
  - `scripts/sammed3d_prompt_infer_dataset.py`
  - `scripts/sammed3d_sparse_prompt_infer_dataset.py`

- Metric calculation and summarization:
  - `scripts/evaluate_segmentation_folder.py`
  - `scripts/evaluate_segmentation_dice_only.py`
  - `scripts/summarize_ctv_main_experiment_results.py`
  - `scripts/summarize_oar_baselines_with_optional_methods.py`
  - `scripts/summarize_completed_segmentation_results.py`

## Visualization and Manuscript Figures

- CTV all-method and ablation figures:
  - `scripts/generate_pr_visual_figures.py`
  - output: `manuscript_pr_biomedical_data_refine_20260603/figures/method_visual_comparison_example.png`
  - output: `manuscript_pr_biomedical_data_refine_20260603/figures/ablation_visual_progression_example.png`

- CTV test-set HTML visualization:
  - `scripts/create_ctv_html_visualization.py`
  - output: `reports/html_ctv_visualization/index.html`

- OAR test-set HTML visualization:
  - `scripts/create_oar_html_visualization.py`
  - output: `reports/html_oar_visualization/index.html`

- GTV/CTV target-hierarchy audit package:
  - `gtv_ctv_repro_package_20260604/visualize_gtv_ctv_targets.py`
  - `gtv_ctv_repro_package_20260604/code/visualize_gtv_ctv_targets.py`
  - output: `gtv_ctv_repro_package_20260604/outputs/gtv_ctv_target_visualization/`

## Current Manuscript Package

- Main manuscript:
  - `manuscript_pr_biomedical_data_refine_20260603/main.tex`

- Main tables:
  - `manuscript_pr_biomedical_data_refine_20260603/tables/main_ctv_results.tex`
  - `manuscript_pr_biomedical_data_refine_20260603/tables/ablation_summary.tex`
  - `manuscript_pr_biomedical_data_refine_20260603/tables/oar_context_results.tex`
  - `manuscript_pr_biomedical_data_refine_20260603/tables/refine_statistics.tex`

- Added/required visual figures:
  - `manuscript_pr_biomedical_data_refine_20260603/figures/gtv_ctv_difference_example.png`
  - `manuscript_pr_biomedical_data_refine_20260603/figures/method_visual_comparison_example.png`
  - `manuscript_pr_biomedical_data_refine_20260603/figures/ablation_visual_progression_example.png`
  - `manuscript_pr_biomedical_data_refine_20260603/figures/oar_example_*.png`
