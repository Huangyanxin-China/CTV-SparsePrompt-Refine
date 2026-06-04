#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
NNUNET_SRC="${NNUNET_SRC:-/share3/home/huangyanxin/nnUNet}"
CONDA_ENV="${CONDA_ENV:-umamba}"
CONFIG="${CONFIG:-3d_fullres}"
PLANS="${PLANS:-nnUNetPlans}"
TRAINER="${TRAINER:-nnUNetTrainer}"
MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl_nnunet_test}"

RAW_ROOT="${RAW_ROOT:-${PROJECT_ROOT}/nnunet_runs/raw}"

log() {
    printf '[%(%F %T)T] %s\n' -1 "$*"
}

nnunet_env() {
    local dataset_name="$1"
    shift
    PYTHONPATH="${PROJECT_ROOT}/python_compat:${NNUNET_SRC}:${PYTHONPATH:-}" \
    nnUNet_raw="${RAW_ROOT}" \
    nnUNet_preprocessed="${PROJECT_ROOT}/nnunet_runs/${dataset_name}/preprocessed" \
    nnUNet_results="${PROJECT_ROOT}/nnunet_runs/${dataset_name}/results" \
    MPLCONFIGDIR="${MPLCONFIGDIR}" \
    "$@"
}

predict_and_eval() {
    local task="$1"
    local dataset_id="$2"
    local dataset_name="$3"
    local folds="$4"
    local gpu="$5"
    local method_key="$6"
    shift 6
    local classes=("$@")

    local img_dir="${RAW_ROOT}/${dataset_name}/imagesTs"
    local gt_dir="${RAW_ROOT}/${dataset_name}/labelsTs"
    local pred_dir="${PROJECT_ROOT}/external_runs/nnunet/${method_key}/${task}"
    local metrics_dir="${PROJECT_ROOT}/external_runs/metrics/${method_key}/${task}"

    mkdir -p "${pred_dir}" "${metrics_dir}" "${MPLCONFIGDIR}"

    log "Predicting ${task}: dataset=${dataset_name}, folds=${folds}, gpu=${gpu}, out=${pred_dir}"
    # shellcheck disable=SC2086
    CUDA_VISIBLE_DEVICES="${gpu}" nnunet_env "${dataset_name}" conda run -n "${CONDA_ENV}" nnUNetv2_predict \
        -i "${img_dir}" \
        -o "${pred_dir}" \
        -d "${dataset_id}" \
        -c "${CONFIG}" \
        -p "${PLANS}" \
        -tr "${TRAINER}" \
        -f ${folds} \
        -chk checkpoint_final.pth \
        -device cuda \
        --disable_progress_bar

    log "Evaluating ${task} globally against ${gt_dir}"
    local class_names=()
    if [[ "${task}" == "ctv" ]]; then
        class_names=(ctv)
    else
        class_names=(lung heart spinal esophagus)
    fi

    conda run -n "${CONDA_ENV}" python "${PROJECT_ROOT}/scripts/evaluate_segmentation_folder.py" \
        --gt_dir "${gt_dir}" \
        --pred_dir "${pred_dir}" \
        --classes "${classes[@]}" \
        --class_names "${class_names[@]}" \
        --output_csv "${metrics_dir}/per_case.csv" \
        --output_json "${metrics_dir}/summary.json"
}

stage="${1:-all}"
case "${stage}" in
    ctv)
        predict_and_eval ctv 15 Dataset015_CTV_Dataset004Split "0 1 2" "${NNUNET_CTV_GPU:-2}" nnunet_3d_fullres_folds012_final 1
        ;;
    oar)
        predict_and_eval oar 14 Dataset014_ThoracicOAR_Dataset004Split "2 3 4" "${NNUNET_OAR_GPU:-3}" nnunet_3d_fullres_folds234_final 1 2 3 4
        ;;
    all)
        predict_and_eval ctv 15 Dataset015_CTV_Dataset004Split "0 1 2" "${NNUNET_CTV_GPU:-2}" nnunet_3d_fullres_folds012_final 1
        predict_and_eval oar 14 Dataset014_ThoracicOAR_Dataset004Split "2 3 4" "${NNUNET_OAR_GPU:-3}" nnunet_3d_fullres_folds234_final 1 2 3 4
        ;;
    *)
        echo "Unknown stage: ${stage}. Use ctv, oar, or all." >&2
        exit 1
        ;;
esac
