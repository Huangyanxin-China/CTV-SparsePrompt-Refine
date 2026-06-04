#!/usr/bin/env bash
set -euo pipefail

# End-to-end nnU-Net v2 workflow for Dataset004:
# 1) create an nnU-Net-v2-compatible raw-data mirror
# 2) plan and preprocess 3d_fullres
# 3) train 5 folds in parallel
# 4) predict imagesTs with fold ensemble
# 5) evaluate labelsTs and summarize CTV metrics

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DATASET_ID="${DATASET_ID:-4}"
DATASET_NAME="${DATASET_NAME:-Dataset004_ThoracicOARCTV_OneCaseTrain}"
CONFIG="${CONFIG:-3d_fullres}"
PLANS="${PLANS:-nnUNetPlans}"
TRAINER="${TRAINER:-nnUNetTrainer}"
CONDA_ENV="${CONDA_ENV:-umamba}"
NNUNET_SRC="${NNUNET_SRC:-/share3/home/huangyanxin/nnUNet}"

SOURCE_DATASET="${SOURCE_DATASET:-/share3/home/huangyanxin/nnUNet/DATASET/nnUNet_raw/${DATASET_NAME}}"
RAW_ROOT="${RAW_ROOT:-${PROJECT_ROOT}/nnunet_runs/raw}"
RUN_ROOT="${RUN_ROOT:-${PROJECT_ROOT}/nnunet_runs/${DATASET_NAME}}"
PREPROCESSED_ROOT="${PREPROCESSED_ROOT:-${RUN_ROOT}/preprocessed}"
RESULTS_ROOT="${RESULTS_ROOT:-${RUN_ROOT}/results}"
PRED_ROOT="${PRED_ROOT:-${RUN_ROOT}/predictions_${CONFIG}}"
LOG_ROOT="${LOG_ROOT:-${PROJECT_ROOT}/logs/nnunet_dataset004_${CONFIG}}"
MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl_nnunet_dataset004}"

GPU_LIST="${GPU_LIST:-0,1,2,3,4,5,6,7}"
FOLD_LIST="${FOLD_LIST:-0 1 2 3 4}"
PRED_NUM_PARTS="${PRED_NUM_PARTS:-8}"
NPFP="${NPFP:-4}"
NP_PREPROCESS="${NP_PREPROCESS:-4}"
NP_EVAL="${NP_EVAL:-8}"
SAVE_PROBABILITIES="${SAVE_PROBABILITIES:-1}"
CONTINUE_TRAINING="${CONTINUE_TRAINING:-1}"
TRAIN_START_DELAY="${TRAIN_START_DELAY:-60}"

RAW_DATASET="${RAW_ROOT}/${DATASET_NAME}"
IMAGES_TS="${RAW_DATASET}/imagesTs"
LABELS_TS="${RAW_DATASET}/labelsTs"
PRED_DIR="${PRED_ROOT}/multiclass_${CONFIG}"
SUMMARY_JSON="${PRED_DIR}/summary.json"
SUMMARY_DIR="${PRED_ROOT}/summary"

usage() {
    cat <<EOF
Usage:
  bash scripts/run_dataset004_nnunet_server05.sh [stage]

Stages:
  all          mirror + preflight + preprocess + train + predict + evaluate
  mirror       create raw-data mirror with nnU-Net v2 dataset.json
  preflight    check conda env, package imports and GPU visibility
  preprocess   nnUNetv2_plan_and_preprocess
  train        train folds listed in FOLD_LIST in parallel
  predict      ensemble-predict imagesTs with trained folds
  evaluate     evaluate labelsTs vs predictions and write CSV summaries

Common overrides:
  CONDA_ENV=umamba
  NNUNET_SRC=/share3/home/huangyanxin/nnUNet
  GPU_LIST=0,1,2,3,4,5,6,7
  FOLD_LIST="0 1 2 3 4"
  PRED_NUM_PARTS=8

Example on server05:
  cd ${PROJECT_ROOT}
  GPU_LIST=0,1,2,3,4,5,6,7 bash scripts/run_dataset004_nnunet_server05.sh all
EOF
}

log() {
    printf '[%(%F %T)T] %s\n' -1 "$*"
}

split_gpus() {
    IFS=',' read -r -a GPUS <<< "${GPU_LIST}"
    if [[ "${#GPUS[@]}" -eq 0 ]]; then
        echo "GPU_LIST is empty" >&2
        exit 1
    fi
}

nnunet_env() {
    PYTHONPATH="${NNUNET_SRC}:${PYTHONPATH:-}" \
    nnUNet_raw="${RAW_ROOT}" \
    nnUNet_preprocessed="${PREPROCESSED_ROOT}" \
    nnUNet_results="${RESULTS_ROOT}" \
    MPLCONFIGDIR="${MPLCONFIGDIR}" \
    "$@"
}

nnunet_cmd() {
    nnunet_env conda run -n "${CONDA_ENV}" "$@"
}

ensure_raw_mirror() {
    log "Creating raw-data mirror at ${RAW_DATASET}"
    mkdir -p "${RAW_DATASET}" "${RAW_ROOT}" "${RUN_ROOT}" "${PREPROCESSED_ROOT}" "${RESULTS_ROOT}" "${PRED_ROOT}" "${LOG_ROOT}" "${MPLCONFIGDIR}"

    if [[ ! -d "${SOURCE_DATASET}" ]]; then
        echo "Source dataset not found: ${SOURCE_DATASET}" >&2
        exit 1
    fi

    for subdir in imagesTr labelsTr imagesTs labelsTs; do
        rm -rf "${RAW_DATASET:?}/${subdir}"
        ln -s "${SOURCE_DATASET}/${subdir}" "${RAW_DATASET}/${subdir}"
    done

    cat > "${RAW_DATASET}/dataset.json" <<'EOF'
{
    "channel_names": {
        "0": "CT"
    },
    "labels": {
        "background": 0,
        "lung": 1,
        "heart": 2,
        "spinal": 3,
        "esophagus": 4,
        "ctv": 5
    },
    "numTraining": 34,
    "file_ending": ".nii.gz",
    "overwrite_image_reader_writer": "SimpleITKIO",
    "name": "Dataset004_ThoracicOARCTV_OneCaseTrain"
}
EOF

    log "Training images: $(find -L "${RAW_DATASET}/imagesTr" -maxdepth 1 -type f | wc -l)"
    log "Training labels: $(find -L "${RAW_DATASET}/labelsTr" -maxdepth 1 -type f | wc -l)"
    log "Test images:     $(find -L "${RAW_DATASET}/imagesTs" -maxdepth 1 -type f | wc -l)"
    log "Test labels:     $(find -L "${RAW_DATASET}/labelsTs" -maxdepth 1 -type f | wc -l)"
}

preflight() {
    log "Project root: ${PROJECT_ROOT}"
    log "Conda env: ${CONDA_ENV}"
    log "nnU-Net source: ${NNUNET_SRC}"
    log "Raw root: ${RAW_ROOT}"
    log "Preprocessed root: ${PREPROCESSED_ROOT}"
    log "Results root: ${RESULTS_ROOT}"
    log "GPU list: ${GPU_LIST}"

    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader || true
    else
        log "nvidia-smi not found"
    fi

    nnunet_cmd python - <<'PY'
import importlib
mods = ["torch", "nnunetv2", "SimpleITK", "batchgenerators", "batchgeneratorsv2"]
for mod in mods:
    try:
        m = importlib.import_module(mod)
        print(f"{mod}: OK {getattr(m, '__file__', '')}")
    except Exception as e:
        raise SystemExit(f"{mod}: FAILED: {e}")
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("cuda device count:", torch.cuda.device_count())
PY
}

preprocess() {
    log "Running nnUNetv2_plan_and_preprocess for Dataset${DATASET_ID}, config=${CONFIG}"
    nnunet_cmd nnUNetv2_plan_and_preprocess \
        -d "${DATASET_ID}" \
        -c "${CONFIG}" \
        --verify_dataset_integrity \
        -npfp "${NPFP}" \
        -np "${NP_PREPROCESS}" \
        2>&1 | tee "${LOG_ROOT}/preprocess_${CONFIG}.log"
}

train_one_fold() {
    local fold="$1"
    local gpu="$2"
    local log_file="${LOG_ROOT}/train_fold${fold}_${CONFIG}.log"
    local continue_args=()
    if [[ "${CONTINUE_TRAINING}" == "1" ]]; then
        continue_args+=(--c)
    fi

    log "Starting fold ${fold} on GPU ${gpu}; log=${log_file}"
    CUDA_VISIBLE_DEVICES="${gpu}" \
    nnunet_env conda run -n "${CONDA_ENV}" nnUNetv2_train \
        "${DATASET_ID}" "${CONFIG}" "${fold}" \
        -p "${PLANS}" \
        -tr "${TRAINER}" \
        --npz \
        "${continue_args[@]}" \
        -device cuda \
        > "${log_file}" 2>&1
}

train_folds() {
    split_gpus
    mkdir -p "${LOG_ROOT}"

    local -a folds=(${FOLD_LIST})
    local -a pids=()
    for i in "${!folds[@]}"; do
        local fold="${folds[$i]}"
        local gpu="${GPUS[$((i % ${#GPUS[@]}))]}"
        train_one_fold "${fold}" "${gpu}" &
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

predict_test() {
    split_gpus
    mkdir -p "${PRED_DIR}" "${LOG_ROOT}"

    local -a folds=(${FOLD_LIST})
    local fold_args=()
    for fold in "${folds[@]}"; do
        fold_args+=("${fold}")
    done

    local prob_args=()
    if [[ "${SAVE_PROBABILITIES}" == "1" ]]; then
        prob_args+=(--save_probabilities)
    fi

    local -a pids=()
    for ((part=0; part<PRED_NUM_PARTS; part++)); do
        local gpu="${GPUS[$((part % ${#GPUS[@]}))]}"
        local log_file="${LOG_ROOT}/predict_part${part}_${CONFIG}.log"
        log "Starting prediction part ${part}/${PRED_NUM_PARTS} on GPU ${gpu}; log=${log_file}"
        CUDA_VISIBLE_DEVICES="${gpu}" \
        nnunet_env conda run -n "${CONDA_ENV}" nnUNetv2_predict \
            -i "${IMAGES_TS}" \
            -o "${PRED_DIR}" \
            -d "${DATASET_ID}" \
            -c "${CONFIG}" \
            -p "${PLANS}" \
            -tr "${TRAINER}" \
            -f "${fold_args[@]}" \
            -num_parts "${PRED_NUM_PARTS}" \
            -part_id "${part}" \
            --continue_prediction \
            "${prob_args[@]}" \
            -device cuda \
            > "${log_file}" 2>&1 &
        pids+=("$!")
        sleep 2
    done

    local failed=0
    for pid in "${pids[@]}"; do
        if ! wait "${pid}"; then
            failed=1
        fi
    done

    if [[ "${failed}" != "0" ]]; then
        echo "At least one prediction part failed. Check ${LOG_ROOT}/predict_part*.log" >&2
        exit 1
    fi
    log "Prediction finished: ${PRED_DIR}"
}

evaluate_test() {
    mkdir -p "${SUMMARY_DIR}"
    local plans_file="${PREPROCESSED_ROOT}/${DATASET_NAME}/${PLANS}.json"
    local dataset_json="${RAW_DATASET}/dataset.json"

    log "Evaluating predictions"
    nnunet_cmd nnUNetv2_evaluate_folder \
        "${LABELS_TS}" \
        "${PRED_DIR}" \
        -djfile "${dataset_json}" \
        -pfile "${plans_file}" \
        -o "${SUMMARY_JSON}" \
        -np "${NP_EVAL}" \
        2>&1 | tee "${LOG_ROOT}/evaluate_${CONFIG}.log"

    nnunet_cmd python "${PROJECT_ROOT}/scripts/summarize_nnunet_summary.py" \
        --summary "${SUMMARY_JSON}" \
        --dataset-json "${dataset_json}" \
        --out-dir "${SUMMARY_DIR}" \
        --target-label 5

    log "Summary JSON: ${SUMMARY_JSON}"
    log "CTV metrics CSV: ${SUMMARY_DIR}/ctv_case_metrics.csv"
    log "Class metrics CSV: ${SUMMARY_DIR}/metrics_per_class.csv"
}

stage="${1:-all}"
case "${stage}" in
    -h|--help|help)
        usage
        ;;
    mirror)
        ensure_raw_mirror
        ;;
    preflight)
        ensure_raw_mirror
        preflight
        ;;
    preprocess)
        ensure_raw_mirror
        preprocess
        ;;
    train)
        train_folds
        ;;
    predict)
        predict_test
        ;;
    evaluate)
        evaluate_test
        ;;
    all)
        ensure_raw_mirror
        preflight
        preprocess
        train_folds
        predict_test
        evaluate_test
        ;;
    *)
        echo "Unknown stage: ${stage}" >&2
        usage >&2
        exit 1
        ;;
esac
