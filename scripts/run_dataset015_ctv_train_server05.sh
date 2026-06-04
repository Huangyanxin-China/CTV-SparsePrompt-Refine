#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
NNUNET_SRC="${NNUNET_SRC:-/share3/home/huangyanxin/nnUNet}"
CONDA_ENV="${CONDA_ENV:-umamba}"

DATASET_ID="${DATASET_ID:-15}"
DATASET_NAME="${DATASET_NAME:-Dataset015_CTV_Dataset004Split}"
CONFIG="${CONFIG:-3d_fullres}"
PLANS="${PLANS:-nnUNetPlans}"
TRAINER="${TRAINER:-nnUNetTrainer}"

RAW_ROOT="${RAW_ROOT:-${PROJECT_ROOT}/nnunet_runs/raw}"
RUN_ROOT="${RUN_ROOT:-${PROJECT_ROOT}/nnunet_runs/${DATASET_NAME}}"
PREPROCESSED_ROOT="${PREPROCESSED_ROOT:-${RUN_ROOT}/preprocessed}"
RESULTS_ROOT="${RESULTS_ROOT:-${RUN_ROOT}/results}"
LOG_ROOT="${LOG_ROOT:-${PROJECT_ROOT}/logs/nnunet_dataset015_ctv_${CONFIG}}"
MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl_nnunet_dataset015}"

GPU_LIST="${GPU_LIST:-5,6,7}"
FOLD_LIST="${FOLD_LIST:-0 1 2}"
NPFP="${NPFP:-4}"
NP_PREPROCESS="${NP_PREPROCESS:-4}"
TRAIN_START_DELAY="${TRAIN_START_DELAY:-30}"

log() {
    printf '[%(%F %T)T] %s\n' -1 "$*"
}

nnunet_env() {
    PYTHONPATH="${PROJECT_ROOT}/python_compat:${NNUNET_SRC}:${PYTHONPATH:-}" \
    nnUNet_raw="${RAW_ROOT}" \
    nnUNet_preprocessed="${PREPROCESSED_ROOT}" \
    nnUNet_results="${RESULTS_ROOT}" \
    MPLCONFIGDIR="${MPLCONFIGDIR}" \
    "$@"
}

split_gpus() {
    IFS=',' read -r -a GPUS <<< "${GPU_LIST}"
    if [[ "${#GPUS[@]}" -eq 0 ]]; then
        echo "GPU_LIST is empty" >&2
        exit 1
    fi
}

preflight() {
    log "PROJECT_ROOT=${PROJECT_ROOT}"
    log "DATASET_ID=${DATASET_ID}"
    log "DATASET_NAME=${DATASET_NAME}"
    log "RAW_ROOT=${RAW_ROOT}"
    log "PREPROCESSED_ROOT=${PREPROCESSED_ROOT}"
    log "RESULTS_ROOT=${RESULTS_ROOT}"
    log "GPU_LIST=${GPU_LIST}"
    log "FOLD_LIST=${FOLD_LIST}"
    mkdir -p "${PREPROCESSED_ROOT}" "${RESULTS_ROOT}" "${LOG_ROOT}" "${MPLCONFIGDIR}"

    if [[ ! -f "${RAW_ROOT}/${DATASET_NAME}/dataset.json" ]]; then
        echo "Missing dataset.json: ${RAW_ROOT}/${DATASET_NAME}/dataset.json" >&2
        exit 1
    fi

    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader || true
    fi

    nnunet_env conda run -n "${CONDA_ENV}" python - <<'PY'
import torch, nnunetv2, batchgeneratorsv2
from torch import GradScaler
print("nnunetv2:", nnunetv2.__file__)
print("torch:", torch.__version__, torch.version.cuda)
print("cuda:", torch.cuda.is_available(), torch.cuda.device_count())
print("GradScaler:", GradScaler)
PY
}

preprocess() {
    local done_file="${LOG_ROOT}/preprocess_${CONFIG}.done"
    if [[ -f "${done_file}" ]]; then
        log "Preprocess already marked done: ${done_file}"
        return
    fi

    log "Running plan_and_preprocess for Dataset${DATASET_ID} ${CONFIG}"
    nnunet_env conda run -n "${CONDA_ENV}" nnUNetv2_plan_and_preprocess \
        -d "${DATASET_ID}" \
        -c "${CONFIG}" \
        --verify_dataset_integrity \
        -npfp "${NPFP}" \
        -np "${NP_PREPROCESS}" \
        2>&1 | tee "${LOG_ROOT}/preprocess_${CONFIG}.log"

    touch "${done_file}"
}

train_fold() {
    local fold="$1"
    local gpu="$2"
    local log_file="${LOG_ROOT}/train_fold${fold}_${CONFIG}.log"
    log "Starting fold ${fold} on GPU ${gpu}; log=${log_file}"
    CUDA_VISIBLE_DEVICES="${gpu}" \
    nnunet_env conda run -n "${CONDA_ENV}" nnUNetv2_train \
        "${DATASET_ID}" "${CONFIG}" "${fold}" \
        -p "${PLANS}" \
        -tr "${TRAINER}" \
        --npz \
        --c \
        -device cuda \
        > "${log_file}" 2>&1
}

train_all() {
    split_gpus
    local -a folds=(${FOLD_LIST})
    local -a pids=()

    for i in "${!folds[@]}"; do
        local fold="${folds[$i]}"
        local gpu="${GPUS[$((i % ${#GPUS[@]}))]}"
        train_fold "${fold}" "${gpu}" &
        pids+=("$!")
        sleep "${TRAIN_START_DELAY}"
    done

    local failed=0
    for pid in "${pids[@]}"; do
        if ! wait "${pid}"; then
            failed=1
        fi
    done

    if [[ "${failed}" != "0" ]]; then
        echo "At least one fold failed. Check ${LOG_ROOT}/train_fold*.log" >&2
        exit 1
    fi
    log "All requested folds finished"
}

stage="${1:-all}"
case "${stage}" in
    preflight) preflight ;;
    preprocess) preflight; preprocess ;;
    train) preflight; train_all ;;
    all) preflight; preprocess; train_all ;;
    *)
        echo "Unknown stage: ${stage}" >&2
        exit 1
        ;;
esac
