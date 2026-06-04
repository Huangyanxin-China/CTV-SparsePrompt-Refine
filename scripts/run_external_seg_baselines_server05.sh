#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RAW_ROOT="${RAW_ROOT:-$PROJECT_ROOT/nnunet_runs/raw}"

UMAMBA_REPO="${UMAMBA_REPO:-/share3/home/huangyanxin/U-Mamba}"
SAM_REPO="${SAM_REPO:-/share3/home/huangyanxin/SAM-Med3D-main}"
DIFFUNET_REPO="${DIFFUNET_REPO:-/share3/home/huangyanxin/DiffUNet-main}"

UMAMBA_ENV="${UMAMBA_ENV:-umamba}"
SAM_ENV="${SAM_ENV:-sammed3d}"
DIFFUNET_ENV="${DIFFUNET_ENV:-diffunet}"

RUN_ROOT="${RUN_ROOT:-$PROJECT_ROOT/external_runs}"
LOG_ROOT="${LOG_ROOT:-$PROJECT_ROOT/logs/external_baselines}"

UMAMBA_TRAINER="${UMAMBA_TRAINER:-nnUNetTrainerUMambaEncNoAMP}"
UMAMBA_GPUS="${UMAMBA_GPUS:-0,1,2,3,4}"
UMAMBA_FOLDS="${UMAMBA_FOLDS:-0 1 2 3 4}"
UMAMBA_CONFIG="${UMAMBA_CONFIG:-3d_fullres}"

SAM_GPUS="${SAM_GPUS:-0}"
SAM_MULTI_GPU="${SAM_MULTI_GPU:-0}"
SAM_EPOCHS="${SAM_EPOCHS:-100}"
SAM_BATCH_SIZE="${SAM_BATCH_SIZE:-2}"
SAM_NUM_WORKERS="${SAM_NUM_WORKERS:-4}"
SAM_LR="${SAM_LR:-1e-5}"
SAM_NUM_CLICKS="${SAM_NUM_CLICKS:-10}"
SAM_NONORACLE_CLICKS="${SAM_NONORACLE_CLICKS:-1}"
SAM_NONORACLE_PROMPT_MODE="${SAM_NONORACLE_PROMPT_MODE:-ct_heuristic}"
SAM_CKPT="${SAM_CKPT:-$SAM_REPO/ckpt/sam_med3d_turbo.pth}"

DIFFUNET_GPU="${DIFFUNET_GPU:-0}"
DIFFUNET_EPOCHS="${DIFFUNET_EPOCHS:-100}"
DIFFUNET_BATCH_SIZE="${DIFFUNET_BATCH_SIZE:-2}"
DIFFUNET_STEPS_PER_EPOCH="${DIFFUNET_STEPS_PER_EPOCH:-250}"
DIFFUNET_VAL_EVERY="${DIFFUNET_VAL_EVERY:-4}"

mkdir -p "$RUN_ROOT" "$LOG_ROOT"

usage() {
    cat <<'EOF'
Usage:
  bash scripts/run_external_seg_baselines_server05.sh check
  bash scripts/run_external_seg_baselines_server05.sh umamba_prepare  [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh umamba_train    [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh umamba_predict  [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh umamba_eval     [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh umamba_all      [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh sam_train       [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh sam_prompt_test [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh sam_nonoracle_test [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh sam_eval        [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh sam_all         [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh diff_prepare    [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh diff_train      [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh diff_predict    [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh diff_eval       [oar|ctv|all]
  bash scripts/run_external_seg_baselines_server05.sh diff_all        [oar|ctv|all]

Examples:
  UMAMBA_GPUS=2,3,4,5,6 bash scripts/run_external_seg_baselines_server05.sh umamba_all ctv
  SAM_GPUS="0 1 2 3" SAM_MULTI_GPU=1 bash scripts/run_external_seg_baselines_server05.sh sam_all ctv
  DIFFUNET_GPU=7 bash scripts/run_external_seg_baselines_server05.sh diff_all ctv
EOF
}

set_task() {
    local task="$1"
    case "$task" in
        oar)
            TASK="oar"
            DATASET_ID="14"
            DATASET_NAME="Dataset014_ThoracicOAR_Dataset004Split"
            RAW_DIR="$RAW_ROOT/$DATASET_NAME"
            CLASSES=(1 2 3 4)
            CLASS_NAMES=(lung heart spinal esophagus)
            OUT_CHANNELS="5"
            ;;
        ctv)
            TASK="ctv"
            DATASET_ID="15"
            DATASET_NAME="Dataset015_CTV_Dataset004Split"
            RAW_DIR="$RAW_ROOT/$DATASET_NAME"
            CLASSES=(1)
            CLASS_NAMES=(ctv)
            OUT_CHANNELS="2"
            ;;
        *)
            echo "Unknown task: $task" >&2
            exit 2
            ;;
    esac
}

for_each_task() {
    local task="$1"
    local fn="$2"
    if [[ "$task" == "all" ]]; then
        "$fn" oar
        "$fn" ctv
    else
        "$fn" "$task"
    fi
}

check_paths() {
    echo "PROJECT_ROOT=$PROJECT_ROOT"
    echo "U-Mamba repo: $UMAMBA_REPO"
    echo "SAM-Med3D repo: $SAM_REPO"
    echo "DiffUNet repo: $DIFFUNET_REPO"
    echo "Dataset014: $RAW_ROOT/Dataset014_ThoracicOAR_Dataset004Split"
    echo "Dataset015: $RAW_ROOT/Dataset015_CTV_Dataset004Split"
    for path in \
        "$UMAMBA_REPO/umamba/nnunetv2" \
        "$SAM_REPO/train.py" \
        "$SAM_REPO/utils/infer_utils.py" \
        "$DIFFUNET_REPO/diffunet/diffunet_model.py" \
        "$RAW_ROOT/Dataset014_ThoracicOAR_Dataset004Split/imagesTr" \
        "$RAW_ROOT/Dataset014_ThoracicOAR_Dataset004Split/imagesTs" \
        "$RAW_ROOT/Dataset015_CTV_Dataset004Split/imagesTr" \
        "$RAW_ROOT/Dataset015_CTV_Dataset004Split/imagesTs"; do
        if [[ -e "$path" ]]; then
            echo "[OK] $path"
        else
            echo "[MISSING] $path"
        fi
    done
}

umamba_cmd_prefix() {
    local cuda_env=()
    if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
        cuda_env=(CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES")
    fi
    env \
        "${cuda_env[@]}" \
        PYTHONPATH="$PROJECT_ROOT/python_compat:$UMAMBA_REPO/umamba:${PYTHONPATH:-}" \
        nnUNet_raw="$RAW_ROOT" \
        nnUNet_preprocessed="$RUN_ROOT/umamba/preprocessed" \
        nnUNet_results="$RUN_ROOT/umamba/results" \
        MPLCONFIGDIR="/tmp/mpl_umamba_${USER:-user}" \
        conda run -n "$UMAMBA_ENV" "$@"
}

umamba_prepare_one() {
    set_task "$1"
    mkdir -p "$RUN_ROOT/umamba/preprocessed" "$RUN_ROOT/umamba/results"
    echo "Planning/preprocessing U-Mamba $TASK Dataset$DATASET_ID"
    umamba_cmd_prefix nnUNetv2_plan_and_preprocess -d "$DATASET_ID" --verify_dataset_integrity
}

umamba_train_one() {
    set_task "$1"
    mkdir -p "$LOG_ROOT/umamba_$TASK"
    IFS=',' read -r -a gpu_array <<< "$UMAMBA_GPUS"
    read -r -a fold_array <<< "$UMAMBA_FOLDS"
    local idx=0
    for fold in "${fold_array[@]}"; do
        local gpu="${gpu_array[$((idx % ${#gpu_array[@]}))]}"
        local log="$LOG_ROOT/umamba_$TASK/fold_${fold}.log"
        echo "Launching U-Mamba $TASK fold $fold on GPU $gpu -> $log"
        (
            CUDA_VISIBLE_DEVICES="$gpu" umamba_cmd_prefix \
                nnUNetv2_train "$DATASET_ID" "$UMAMBA_CONFIG" "$fold" \
                -tr "$UMAMBA_TRAINER" --npz
        ) > "$log" 2>&1 &
        idx=$((idx + 1))
    done
    wait
}

umamba_predict_one() {
    set_task "$1"
    local out_dir="$RUN_ROOT/umamba/predictions/$TASK"
    mkdir -p "$out_dir"
    echo "Predicting U-Mamba $TASK -> $out_dir"
    umamba_cmd_prefix nnUNetv2_predict \
        -i "$RAW_DIR/imagesTs" \
        -o "$out_dir" \
        -d "$DATASET_ID" \
        -c "$UMAMBA_CONFIG" \
        -f 0 1 2 3 4 \
        -tr "$UMAMBA_TRAINER" \
        --disable_tta
}

eval_one() {
    local method="$1"
    local task="$2"
    local pred_dir="$3"
    set_task "$task"
    local metric_dir="$RUN_ROOT/metrics/$method/$TASK"
    mkdir -p "$metric_dir"
    conda run -n "$DIFFUNET_ENV" python "$PROJECT_ROOT/scripts/evaluate_segmentation_folder.py" \
        --gt_dir "$RAW_DIR/labelsTs" \
        --pred_dir "$pred_dir" \
        --classes "${CLASSES[@]}" \
        --class_names "${CLASS_NAMES[@]}" \
        --output_csv "$metric_dir/per_case.csv" \
        --output_json "$metric_dir/summary.json"
}

umamba_eval_one() {
    set_task "$1"
    eval_one "umamba" "$TASK" "$RUN_ROOT/umamba/predictions/$TASK"
}

sam_train_one() {
    set_task "$1"
    local task_name="sammed3d_$TASK"
    local extra=()
    if [[ "$SAM_MULTI_GPU" == "1" ]]; then
        extra+=(--multi_gpu)
    fi
    mkdir -p "$LOG_ROOT/sammed3d" "$RUN_ROOT/sammed3d/work_dir"
    echo "Training SAM-Med3D $TASK"
    conda run -n "$SAM_ENV" python "$PROJECT_ROOT/scripts/sammed3d_train_with_paths.py" \
        --repo "$SAM_REPO" \
        --data_paths "$RAW_DIR" \
        --task_name "$task_name" \
        --work_dir "$RUN_ROOT/sammed3d/work_dir" \
        --checkpoint "$SAM_CKPT" \
        --gpu_ids $SAM_GPUS \
        --batch_size "$SAM_BATCH_SIZE" \
        --num_workers "$SAM_NUM_WORKERS" \
        --num_epochs "$SAM_EPOCHS" \
        --lr "$SAM_LR" \
        "${extra[@]}" \
        > "$LOG_ROOT/sammed3d/${TASK}_train.log" 2>&1
}

sam_prompt_test_one() {
    set_task "$1"
    local task_name="sammed3d_$TASK"
    local ckpt="$RUN_ROOT/sammed3d/work_dir/$task_name/sam_model_dice_best.pth"
    local out_dir="$RUN_ROOT/sammed3d/predictions/${TASK}_click${SAM_NUM_CLICKS}"
    if [[ ! -f "$ckpt" ]]; then
        echo "Missing SAM checkpoint: $ckpt" >&2
        exit 2
    fi
    mkdir -p "$out_dir" "$LOG_ROOT/sammed3d"
    echo "Prompt-testing SAM-Med3D $TASK with $SAM_NUM_CLICKS GT-derived clicks"
    conda run -n "$SAM_ENV" python "$PROJECT_ROOT/scripts/sammed3d_prompt_infer_dataset.py" \
        --repo "$SAM_REPO" \
        --img_dir "$RAW_DIR/imagesTs" \
        --gt_dir "$RAW_DIR/labelsTs" \
        --out_dir "$out_dir" \
        --ckpt "$ckpt" \
        --num_clicks "$SAM_NUM_CLICKS" \
        > "$LOG_ROOT/sammed3d/${TASK}_prompt_test.log" 2>&1
}

sam_eval_one() {
    set_task "$1"
    eval_one "sammed3d_click${SAM_NUM_CLICKS}" "$TASK" "$RUN_ROOT/sammed3d/predictions/${TASK}_click${SAM_NUM_CLICKS}"
}

sam_nonoracle_test_one() {
    set_task "$1"
    local task_name="sammed3d_$TASK"
    local ckpt="$RUN_ROOT/sammed3d/work_dir/$task_name/sam_model_dice_best.pth"
    local out_dir="$RUN_ROOT/sammed3d_nonoracle/${TASK}_${SAM_NONORACLE_PROMPT_MODE}_click${SAM_NONORACLE_CLICKS}"
    if [[ ! -f "$ckpt" ]]; then
        echo "Missing SAM checkpoint: $ckpt" >&2
        exit 2
    fi
    mkdir -p "$out_dir" "$LOG_ROOT/sammed3d_nonoracle"
    echo "Non-oracle testing SAM-Med3D $TASK with $SAM_NONORACLE_PROMPT_MODE prompts and $SAM_NONORACLE_CLICKS click(s)"
    conda run -n "$SAM_ENV" python "$PROJECT_ROOT/scripts/sammed3d_nonoracle_infer_dataset.py" \
        --repo "$SAM_REPO" \
        --project_root "$PROJECT_ROOT" \
        --task "$TASK" \
        --img_dir "$RAW_DIR/imagesTs" \
        --gt_dir "$RAW_DIR/labelsTs" \
        --out_dir "$out_dir" \
        --ckpt "$ckpt" \
        --prompt_mode "$SAM_NONORACLE_PROMPT_MODE" \
        --num_clicks "$SAM_NONORACLE_CLICKS" \
        --output_csv "$RUN_ROOT/metrics/sammed3d_nonoracle_${SAM_NONORACLE_PROMPT_MODE}_click${SAM_NONORACLE_CLICKS}/$TASK/per_case.csv" \
        --output_json "$RUN_ROOT/metrics/sammed3d_nonoracle_${SAM_NONORACLE_PROMPT_MODE}_click${SAM_NONORACLE_CLICKS}/$TASK/summary.json" \
        > "$LOG_ROOT/sammed3d_nonoracle/${TASK}_${SAM_NONORACLE_PROMPT_MODE}_click${SAM_NONORACLE_CLICKS}.log" 2>&1
}

diff_prepare_one() {
    set_task "$1"
    local base="$RUN_ROOT/diffunet/$TASK"
    mkdir -p "$base/data" "$base/preprocess_work"
    echo "Preprocessing DiffUNet $TASK train"
    conda run -n "$DIFFUNET_ENV" python "$PROJECT_ROOT/scripts/diffunet_preprocess_dataset.py" \
        --repo "$DIFFUNET_REPO" \
        --raw_dataset "$RAW_DIR" \
        --image_dir imagesTr \
        --label_dir labelsTr \
        --output_dir "$base/data/train" \
        --work_dir "$base/preprocess_work" \
        --labels "${CLASSES[@]}"
    echo "Preprocessing DiffUNet $TASK test with train-set analysis"
    conda run -n "$DIFFUNET_ENV" python "$PROJECT_ROOT/scripts/diffunet_preprocess_dataset.py" \
        --repo "$DIFFUNET_REPO" \
        --raw_dataset "$RAW_DIR" \
        --image_dir imagesTs \
        --label_dir labelsTs \
        --output_dir "$base/data/test" \
        --work_dir "$base/preprocess_work" \
        --labels "${CLASSES[@]}"
}

diff_train_one() {
    set_task "$1"
    local base="$RUN_ROOT/diffunet/$TASK"
    mkdir -p "$base/logs"
    echo "Training DiffUNet $TASK on GPU $DIFFUNET_GPU"
    CUDA_VISIBLE_DEVICES="$DIFFUNET_GPU" conda run -n "$DIFFUNET_ENV" python "$PROJECT_ROOT/scripts/diffunet_train_dataset.py" \
        --repo "$DIFFUNET_REPO" \
        --train_dir "$base/data/train" \
        --logdir "$base/logs" \
        --out_channels "$OUT_CHANNELS" \
        --max_epoch "$DIFFUNET_EPOCHS" \
        --batch_size "$DIFFUNET_BATCH_SIZE" \
        --val_every "$DIFFUNET_VAL_EVERY" \
        --steps_per_epoch "$DIFFUNET_STEPS_PER_EPOCH" \
        --device cuda:0 \
        > "$LOG_ROOT/diffunet_${TASK}_train.log" 2>&1
}

latest_diff_model() {
    local model_dir="$1"
    local best
    best="$(ls -t "$model_dir"/best_model_*.pt 2>/dev/null | head -n 1 || true)"
    if [[ -n "$best" ]]; then
        echo "$best"
        return
    fi
    ls -t "$model_dir"/final_model_*.pt 2>/dev/null | head -n 1 || true
}

diff_predict_one() {
    set_task "$1"
    local base="$RUN_ROOT/diffunet/$TASK"
    local model_path
    model_path="$(latest_diff_model "$base/logs/model")"
    if [[ -z "$model_path" ]]; then
        echo "No DiffUNet checkpoint found in $base/logs/model" >&2
        exit 2
    fi
    local out_dir="$base/predictions"
    mkdir -p "$out_dir"
    echo "Predicting DiffUNet $TASK with $model_path"
    CUDA_VISIBLE_DEVICES="$DIFFUNET_GPU" conda run -n "$DIFFUNET_ENV" python "$PROJECT_ROOT/scripts/diffunet_predict_dataset.py" \
        --repo "$DIFFUNET_REPO" \
        --data_dir "$base/data/test" \
        --model_path "$model_path" \
        --out_dir "$out_dir" \
        --out_channels "$OUT_CHANNELS" \
        --device cuda:0 \
        > "$LOG_ROOT/diffunet_${TASK}_predict.log" 2>&1
}

diff_eval_one() {
    set_task "$1"
    eval_one "diffunet" "$TASK" "$RUN_ROOT/diffunet/$TASK/predictions"
}

mode="${1:-}"
task="${2:-all}"

case "$mode" in
    check) check_paths ;;
    umamba_prepare) for_each_task "$task" umamba_prepare_one ;;
    umamba_train) for_each_task "$task" umamba_train_one ;;
    umamba_predict) for_each_task "$task" umamba_predict_one ;;
    umamba_eval) for_each_task "$task" umamba_eval_one ;;
    umamba_all)
        for_each_task "$task" umamba_prepare_one
        for_each_task "$task" umamba_train_one
        for_each_task "$task" umamba_predict_one
        for_each_task "$task" umamba_eval_one
        ;;
    sam_train) for_each_task "$task" sam_train_one ;;
    sam_prompt_test) for_each_task "$task" sam_prompt_test_one ;;
    sam_nonoracle_test) for_each_task "$task" sam_nonoracle_test_one ;;
    sam_eval) for_each_task "$task" sam_eval_one ;;
    sam_all)
        for_each_task "$task" sam_train_one
        for_each_task "$task" sam_prompt_test_one
        for_each_task "$task" sam_eval_one
        ;;
    diff_prepare) for_each_task "$task" diff_prepare_one ;;
    diff_train) for_each_task "$task" diff_train_one ;;
    diff_predict) for_each_task "$task" diff_predict_one ;;
    diff_eval) for_each_task "$task" diff_eval_one ;;
    diff_all)
        for_each_task "$task" diff_prepare_one
        for_each_task "$task" diff_train_one
        for_each_task "$task" diff_predict_one
        for_each_task "$task" diff_eval_one
        ;;
    *) usage; exit 2 ;;
esac
