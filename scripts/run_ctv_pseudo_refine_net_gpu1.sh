#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_ROOT}/../miniconda3/envs/sammed3d/bin/python}"
GPU="${GPU:-1}"
OUT_DIR="${OUT_DIR:-${PROJECT_ROOT}/results/ctv_pseudo_refine_net_k7_oarroi_fastmargin_supervised_gpu${GPU}}"
LOG_DIR="${LOG_DIR:-${PROJECT_ROOT}/logs/ctv_pseudo_refine_net_k7_oarroi_fastmargin_gpu${GPU}}"
TMUX_SESSION="${TMUX_SESSION:-ctv_refine_gpu${GPU}}"

MAX_EPOCHS="${MAX_EPOCHS:-80}"
STEPS_PER_EPOCH="${STEPS_PER_EPOCH:-48}"
VAL_INTERVAL="${VAL_INTERVAL:-5}"
BASE_FILTERS="${BASE_FILTERS:-8}"
PATCH_SIZE="${PATCH_SIZE:-64 128 128}"
ROI_PAD="${ROI_PAD:-12 32 32}"
MIN_ROI="${MIN_ROI:-64 128 128}"
REFINE_MODE="${REFINE_MODE:-fast_margin}"
REFINE_MARGIN_MM="${REFINE_MARGIN_MM:-25}"
ANATOMY_MARGIN_MM="${ANATOMY_MARGIN_MM:-40}"

mkdir -p "${LOG_DIR}" "${OUT_DIR}"

log() {
    printf '[%(%F %T)T] %s\n' -1 "$*"
}

check_gpu() {
    log "PROJECT_ROOT=${PROJECT_ROOT}"
    log "PYTHON_BIN=${PYTHON_BIN}"
    log "GPU=${GPU}"
    log "OUT_DIR=${OUT_DIR}"
    nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits -i "${GPU}" || true
}

dry_run() {
    check_gpu
    log "Running refine dry-run on a small deterministic subset"
    "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/train_ctv_pseudo_refine_net.py" \
        --out_dir "${OUT_DIR}" \
        --case_limit 2 \
        --roi_pad ${ROI_PAD} \
        --min_roi ${MIN_ROI} \
        --patch_size ${PATCH_SIZE} \
        --base_filters "${BASE_FILTERS}" \
        --refine_mode "${REFINE_MODE}" \
        --refine_margin_mm "${REFINE_MARGIN_MM}" \
        --anatomy_margin_mm "${ANATOMY_MARGIN_MM}" \
        --dry_run \
        2>&1 | tee "${LOG_DIR}/dry_run.log"
}

train() {
    check_gpu
    local log_file="${LOG_DIR}/train_gpu${GPU}.log"
    local pid_file="${LOG_DIR}/train_gpu${GPU}.pid"
    log "Launching supervised CTV refine training on GPU ${GPU}; log=${log_file}"
    nohup bash -lc "
        set -o pipefail
        echo '[refine-launch] start='\"\$(date '+%F %T')\"' gpu=${GPU}'
        CUDA_VISIBLE_DEVICES='${GPU}' PYTHONUNBUFFERED=1 \
        '${PYTHON_BIN}' '${PROJECT_ROOT}/scripts/train_ctv_pseudo_refine_net.py' \
            --out_dir '${OUT_DIR}' \
            --roi_pad ${ROI_PAD} \
            --min_roi ${MIN_ROI} \
            --patch_size ${PATCH_SIZE} \
            --base_filters '${BASE_FILTERS}' \
            --refine_mode '${REFINE_MODE}' \
            --refine_margin_mm '${REFINE_MARGIN_MM}' \
            --anatomy_margin_mm '${ANATOMY_MARGIN_MM}' \
            --max_epochs '${MAX_EPOCHS}' \
            --steps_per_epoch '${STEPS_PER_EPOCH}' \
            --val_interval '${VAL_INTERVAL}' \
            --amp
        rc=\$?
        echo '[refine-launch] exit='\"\${rc}\"' end='\"\$(date '+%F %T')\"
        exit \${rc}
    " \
        > "${log_file}" 2>&1 &
    local pid="$!"
    echo "${pid}" > "${pid_file}"
    log "PID=${pid}"
}

tmux_train() {
    check_gpu
    if ! command -v tmux >/dev/null 2>&1; then
        echo "tmux is not available; use train instead." >&2
        exit 2
    fi
    local log_file="${LOG_DIR}/train_gpu${GPU}.log"
    if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
        log "tmux session already exists: ${TMUX_SESSION}"
        return
    fi
    log "Launching tmux session ${TMUX_SESSION} on GPU ${GPU}; log=${log_file}"
    tmux new-session -d -s "${TMUX_SESSION}" "
        cd '${PROJECT_ROOT}'
        set -o pipefail
        echo '[refine-tmux] start='\"\$(date '+%F %T')\"' gpu=${GPU}' | tee '${log_file}'
        CUDA_VISIBLE_DEVICES='${GPU}' PYTHONUNBUFFERED=1 \
        '${PYTHON_BIN}' '${PROJECT_ROOT}/scripts/train_ctv_pseudo_refine_net.py' \
            --out_dir '${OUT_DIR}' \
            --roi_pad ${ROI_PAD} \
            --min_roi ${MIN_ROI} \
            --patch_size ${PATCH_SIZE} \
            --base_filters '${BASE_FILTERS}' \
            --refine_mode '${REFINE_MODE}' \
            --refine_margin_mm '${REFINE_MARGIN_MM}' \
            --anatomy_margin_mm '${ANATOMY_MARGIN_MM}' \
            --max_epochs '${MAX_EPOCHS}' \
            --steps_per_epoch '${STEPS_PER_EPOCH}' \
            --val_interval '${VAL_INTERVAL}' \
            --amp 2>&1 | tee -a '${log_file}'
        rc=\${PIPESTATUS[0]}
        echo '[refine-tmux] exit='\"\${rc}\"' end='\"\$(date '+%F %T')\" | tee -a '${log_file}'
        sleep 5
        exit \${rc}
    "
    log "tmux session started: ${TMUX_SESSION}"
}

status() {
    check_gpu
    if command -v tmux >/dev/null 2>&1; then
        if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
            log "tmux session active: ${TMUX_SESSION}"
        else
            log "tmux session not active: ${TMUX_SESSION}"
        fi
    fi
    if [[ -f "${LOG_DIR}/train_gpu${GPU}.pid" ]]; then
        local pid
        pid="$(cat "${LOG_DIR}/train_gpu${GPU}.pid")"
        log "PID file: ${pid}"
        ps -p "${pid}" -o pid,ppid,stat,etime,cmd || true
    fi
    if [[ -f "${LOG_DIR}/train_gpu${GPU}.log" ]]; then
        log "Last 40 log lines:"
        tail -n 40 "${LOG_DIR}/train_gpu${GPU}.log" || true
    fi
}

stage="${1:-all}"
case "${stage}" in
    dry_run) dry_run ;;
    train) train ;;
    tmux_train) tmux_train ;;
    all) dry_run; train; status ;;
    status) status ;;
    *)
        echo "Usage: $0 {dry_run|train|tmux_train|all|status}" >&2
        exit 2
        ;;
esac
