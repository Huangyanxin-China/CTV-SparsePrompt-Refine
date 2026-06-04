#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${PROJECT_ROOT}"

OUT_ROOT="${1:-results/next_sparse_prompt_core_envelope_workflow}"

python scripts/run_sparse_prompt_core_envelope_workflow.py \
  --ct_dir nnunet_runs/raw/Dataset015_CTV_Dataset004Split/imagesTs \
  --gt_dir nnunet_runs/raw/Dataset015_CTV_Dataset004Split/labelsTs \
  --oar_dir external_runs/nnunet/nnunet_3d_fullres_folds234_final/oar \
  --out_root "${OUT_ROOT}" \
  --k_values 1 3 5 7 9 \
  --strategies even_nonempty max_area_anchors boundary_focused central random_seeded \
  --profiles current mild_expanded endpoint_plateau high_recall \
  --skip_surface_metrics \
  --full_top_n 8 \
  --write_top_predictions

echo "Screening summary: ${OUT_ROOT}/screen/summary.csv"
echo "Oracle-gain ranking: ${OUT_ROOT}/screen/oracle_gain_ranking.csv"
echo "Full top metrics: ${OUT_ROOT}/full_top/summary.csv"
echo "Top prediction masks: ${OUT_ROOT}/full_top/predictions"
