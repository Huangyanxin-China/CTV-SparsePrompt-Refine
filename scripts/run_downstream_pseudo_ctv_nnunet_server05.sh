#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
NNUNET_SRC="${NNUNET_SRC:-/share3/home/huangyanxin/nnUNet}"
CONDA_ENV="${CONDA_ENV:-umamba}"
CONFIG="${CONFIG:-3d_fullres}"
PLANS="${PLANS:-nnUNetPlans}"
TRAINER="${TRAINER:-nnUNetTrainer}"

RAW_ROOT="${RAW_ROOT:-${PROJECT_ROOT}/nnunet_runs/raw}"
RUN_BASE="${RUN_BASE:-${PROJECT_ROOT}/nnunet_runs}"
LOG_ROOT="${LOG_ROOT:-${PROJECT_ROOT}/logs/downstream_pseudo_ctv_nnunet_${CONFIG}}"
MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl_downstream_pseudo_ctv}"
NPFP="${NPFP:-4}"
NP_PREPROCESS="${NP_PREPROCESS:-4}"
GPU_LIST="${GPU_LIST:-4,5,6,7}"
JOB_SPECS="${JOB_SPECS:-16:Dataset016_CTVLinearPseudoK7:0 17:Dataset017_CTVSDFCorePseudoK7:0 18:Dataset018_CTVOursSupportIntersectionK7:0}"
MIN_FREE_MEM_MB="${MIN_FREE_MEM_MB:-10000}"
MAX_GPU_UTIL="${MAX_GPU_UTIL:-40}"

mkdir -p "${LOG_ROOT}" "${MPLCONFIGDIR}"

log() {
    printf '[%(%F %T)T] %s\n' -1 "$*"
}

nnunet_env() {
    local dataset_name="$1"
    shift
    PYTHONPATH="${PROJECT_ROOT}/python_compat:${NNUNET_SRC}:${PYTHONPATH:-}" \
    nnUNet_raw="${RAW_ROOT}" \
    nnUNet_preprocessed="${RUN_BASE}/${dataset_name}/preprocessed" \
    nnUNet_results="${RUN_BASE}/${dataset_name}/results" \
    MPLCONFIGDIR="${MPLCONFIGDIR}" \
    "$@"
}

preflight() {
    log "PROJECT_ROOT=${PROJECT_ROOT}"
    log "NNUNET_SRC=${NNUNET_SRC}"
    log "CONDA_ENV=${CONDA_ENV}"
    log "RAW_ROOT=${RAW_ROOT}"
    log "LOG_ROOT=${LOG_ROOT}"
    log "GPU_LIST=${GPU_LIST}"
    log "JOB_SPECS=${JOB_SPECS}"
    log "MIN_FREE_MEM_MB=${MIN_FREE_MEM_MB}"
    log "MAX_GPU_UTIL=${MAX_GPU_UTIL}"
    nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits || true
    nnunet_env "Dataset016_CTVLinearPseudoK7" conda run -n "${CONDA_ENV}" python - <<'PY'
import torch, nnunetv2
print("nnunetv2:", nnunetv2.__file__)
print("torch:", torch.__version__, torch.version.cuda)
print("cuda probe intentionally skipped in preflight")
PY
}

check_cuda_blockers() {
    local blockers
    blockers="$(
        ps -u "${USER:-huangyanxin}" -o pid,ppid,stat,etime,cmd \
            | awk '$3 ~ /^D/ && ($0 ~ /nnUNetv2_train|torch\\.cuda|python -u -|cuda\\.is_available|cuda\\.device_count/) {print}'
    )"
    if [[ -n "${blockers}" ]]; then
        echo "CUDA appears blocked: found uninterruptible D-state CUDA/python processes." >&2
        echo "${blockers}" >&2
        echo "Do not launch more training jobs until the GPU driver/node has been reset." >&2
        exit 3
    fi
}

split_gpus() {
    IFS=',' read -r -a GPUS <<< "${GPU_LIST}"
    if [[ "${#GPUS[@]}" -eq 0 ]]; then
        echo "GPU_LIST is empty" >&2
        exit 2
    fi
}

check_requested_gpus_free() {
    split_gpus
    local gpu line used total util free unavailable=0
    for gpu in "${GPUS[@]}"; do
        line="$(nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits -i "${gpu}" 2>/dev/null || true)"
        if [[ -z "${line}" ]]; then
            echo "GPU ${gpu}: cannot query nvidia-smi" >&2
            unavailable=1
            continue
        fi
        IFS=',' read -r _idx used total util <<< "${line}"
        used="${used//[[:space:]]/}"
        total="${total//[[:space:]]/}"
        util="${util//[[:space:]]/}"
        free=$((total - used))
        log "GPU ${gpu}: used=${used}MB total=${total}MB free=${free}MB util=${util}%"
        if (( free < MIN_FREE_MEM_MB || util > MAX_GPU_UTIL )); then
            echo "GPU ${gpu} is too busy for downstream training: free=${free}MB, util=${util}%." >&2
            unavailable=1
        fi
    done
    if (( unavailable != 0 )); then
        echo "No launch performed. Override only if intentional, for example MIN_FREE_MEM_MB=3000 MAX_GPU_UTIL=100." >&2
        exit 4
    fi
}

check_raw_dataset() {
    local dataset_name="$1"
    for subdir in imagesTr labelsTr imagesTs labelsTs; do
        if [[ ! -d "${RAW_ROOT}/${dataset_name}/${subdir}" ]]; then
            echo "Missing ${RAW_ROOT}/${dataset_name}/${subdir}" >&2
            exit 2
        fi
    done
    if [[ ! -f "${RAW_ROOT}/${dataset_name}/dataset.json" ]]; then
        echo "Missing ${RAW_ROOT}/${dataset_name}/dataset.json" >&2
        exit 2
    fi
    log "${dataset_name}: imagesTr=$(find -L "${RAW_ROOT}/${dataset_name}/imagesTr" -maxdepth 1 -type f | wc -l), labelsTr=$(find -L "${RAW_ROOT}/${dataset_name}/labelsTr" -maxdepth 1 -type f | wc -l), imagesTs=$(find -L "${RAW_ROOT}/${dataset_name}/imagesTs" -maxdepth 1 -type f | wc -l), labelsTs=$(find -L "${RAW_ROOT}/${dataset_name}/labelsTs" -maxdepth 1 -type f | wc -l)"
}

preprocess_one() {
    local dataset_id="$1"
    local dataset_name="$2"
    local run_root="${RUN_BASE}/${dataset_name}"
    local done_file="${LOG_ROOT}/${dataset_name}_preprocess_${CONFIG}.done"
    mkdir -p "${run_root}/preprocessed" "${run_root}/results" "${LOG_ROOT}"
    check_raw_dataset "${dataset_name}"
    if [[ -f "${done_file}" ]]; then
        log "Preprocess already done for ${dataset_name}: ${done_file}"
        return
    fi
    log "Preprocessing Dataset${dataset_id} ${dataset_name}"
    nnunet_env "${dataset_name}" conda run -n "${CONDA_ENV}" nnUNetv2_plan_and_preprocess \
        -d "${dataset_id}" \
        -c "${CONFIG}" \
        --verify_dataset_integrity \
        -npfp "${NPFP}" \
        -np "${NP_PREPROCESS}" \
        2>&1 | tee "${LOG_ROOT}/${dataset_name}_preprocess_${CONFIG}.log"
    touch "${done_file}"
}

train_one() {
    local dataset_id="$1"
    local dataset_name="$2"
    local fold="$3"
    local gpu="$4"
    local out_dir="${RUN_BASE}/${dataset_name}/results/${dataset_name}/${TRAINER}__${PLANS}__${CONFIG}/fold_${fold}"
    local log_file="${LOG_ROOT}/${dataset_name}_fold${fold}_gpu${gpu}.log"
    local pid_file="${LOG_ROOT}/${dataset_name}_fold${fold}_gpu${gpu}.pid"
    local continue_args=()

    if [[ -f "${out_dir}/checkpoint_final.pth" ]]; then
        log "Skipping ${dataset_name} fold ${fold}: checkpoint_final.pth exists"
        return
    fi
    if [[ -f "${out_dir}/checkpoint_latest.pth" || -f "${out_dir}/checkpoint_best.pth" ]]; then
        continue_args+=(--c)
    fi

    log "Launching ${dataset_name} fold ${fold} on GPU ${gpu}; log=${log_file}"
    nohup env \
        CUDA_VISIBLE_DEVICES="${gpu}" \
        PYTHONPATH="${PROJECT_ROOT}/python_compat:${NNUNET_SRC}:${PYTHONPATH:-}" \
        nnUNet_raw="${RAW_ROOT}" \
        nnUNet_preprocessed="${RUN_BASE}/${dataset_name}/preprocessed" \
        nnUNet_results="${RUN_BASE}/${dataset_name}/results" \
        MPLCONFIGDIR="${MPLCONFIGDIR}" \
        conda run -n "${CONDA_ENV}" nnUNetv2_train \
            "${dataset_id}" "${CONFIG}" "${fold}" \
            -p "${PLANS}" \
            -tr "${TRAINER}" \
            --npz \
            "${continue_args[@]}" \
            -device cuda \
        > "${log_file}" 2>&1 &
    local pid="$!"
    echo "${pid}" > "${pid_file}"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "${pid}" "${gpu}" "${dataset_id}" "${dataset_name}" "${fold}" "${log_file}" >> "${LOG_ROOT}/launched_jobs.tsv"
}

preprocess_all() {
    preprocess_one 16 Dataset016_CTVLinearPseudoK7
    preprocess_one 17 Dataset017_CTVSDFCorePseudoK7
    preprocess_one 18 Dataset018_CTVOursSupportIntersectionK7
}

launch_train_initial() {
    check_cuda_blockers
    check_requested_gpus_free
    : > "${LOG_ROOT}/launched_jobs.tsv"
    local idx=0
    local spec dataset_id dataset_name fold gpu
    for spec in ${JOB_SPECS}; do
        IFS=':' read -r dataset_id dataset_name fold <<< "${spec}"
        gpu="${GPUS[$((idx % ${#GPUS[@]}))]}"
        train_one "${dataset_id}" "${dataset_name}" "${fold}" "${gpu}"
        idx=$((idx + 1))
    done
    log "Initial downstream jobs launched. PID table: ${LOG_ROOT}/launched_jobs.tsv"
}

status() {
    if [[ -f "${LOG_ROOT}/launched_jobs.tsv" ]]; then
        cat "${LOG_ROOT}/launched_jobs.tsv"
    else
        log "No launched_jobs.tsv found"
    fi
    nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits || true
}

stage="${1:-all}"
case "${stage}" in
    preflight) preflight ;;
    preprocess) preflight; preprocess_all ;;
    train) launch_train_initial ;;
    all) preflight; preprocess_all; launch_train_initial; status ;;
    status) status ;;
    *)
        echo "Unknown stage: ${stage}. Use preflight, preprocess, train, all, status." >&2
        exit 2
        ;;
esac
