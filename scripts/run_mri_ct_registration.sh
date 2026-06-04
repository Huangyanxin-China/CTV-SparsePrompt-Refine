#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-/share3/home/huangyanxin/miniconda3/envs/sammed3d/bin/python}"
MRI_ROOT="${MRI_ROOT:-/share3/home/huangyanxin/20260422}"
CT_CSV="${CT_CSV:-data/roi_1mm/roi_1mm.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-data/mri_ct_registration}"

# Use CASE_IDS for exact CT cases, or PATIENT_IDS for all CT cases belonging to
# those patients. Set ALL_PATIENTS=1 to scan all CT rows and register only the
# patients that have matching MRI under MRI_ROOT. Examples:
#   CASE_IDS="patient_EXAMPLE_Lung_CT_YYYYMMDD_0000"
#   PATIENT_IDS="PATIENT_A PATIENT_B"
#   ALL_PATIENTS=1
CASE_IDS="${CASE_IDS:-}"
PATIENT_IDS="${PATIENT_IDS:-}"
ALL_PATIENTS="${ALL_PATIENTS:-0}"
SERIES_KEYWORDS="${SERIES_KEYWORDS:-t2}"
ALL_SERIES="${ALL_SERIES:-0}"
MAX_SERIES_PER_CASE="${MAX_SERIES_PER_CASE:-1}"
MIN_FILES="${MIN_FILES:-10}"
TRANSFORM="${TRANSFORM:-rigid}"
ITERATIONS="${ITERATIONS:-200}"
SAMPLING_PERCENTAGE="${SAMPLING_PERCENTAGE:-0.02}"
LIST_ONLY="${LIST_ONLY:-0}"
OVERWRITE="${OVERWRITE:-0}"

args=(
  --mri_root "${MRI_ROOT}"
  --ct_csv "${CT_CSV}"
  --output_dir "${OUTPUT_DIR}"
  --max_series_per_case "${MAX_SERIES_PER_CASE}"
  --min_files "${MIN_FILES}"
  --transform "${TRANSFORM}"
  --iterations "${ITERATIONS}"
  --sampling_percentage "${SAMPLING_PERCENTAGE}"
)

if [[ -n "${CASE_IDS}" ]]; then
  for case_id in ${CASE_IDS}; do
    args+=(--case_id "${case_id}")
  done
elif [[ "${ALL_PATIENTS}" == "1" ]]; then
  :
else
  if [[ -z "${PATIENT_IDS}" ]]; then
    echo "Set PATIENT_IDS, CASE_IDS, or ALL_PATIENTS=1 before running this local registration helper." >&2
    exit 2
  fi
  for patient_id in ${PATIENT_IDS}; do
    args+=(--patient_id "${patient_id}")
  done
fi

if [[ "${ALL_SERIES}" != "1" ]]; then
  for kw in ${SERIES_KEYWORDS}; do
    args+=(--series_keyword "${kw}")
  done
fi

if [[ "${LIST_ONLY}" == "1" ]]; then
  args+=(--list_only)
fi

if [[ "${OVERWRITE}" == "1" ]]; then
  args+=(--overwrite)
fi

"${PYTHON}" scripts/register_mri_to_ct.py "${args[@]}"
