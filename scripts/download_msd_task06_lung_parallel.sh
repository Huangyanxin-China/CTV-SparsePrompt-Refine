#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-public_data/msd_task06_lung}"
URL="https://msd-for-monai.s3-us-west-2.amazonaws.com/Task06_Lung.tar"
EXPECTED_BYTES="9163696640"
SEGMENTS="${SEGMENTS:-8}"
PART_DIR="${ROOT}/parts"
TAR_PATH="${ROOT}/Task06_Lung.tar"
TMP_TAR="${ROOT}/Task06_Lung.tar.tmp"

mkdir -p "${ROOT}" "${PART_DIR}"

download_part() {
    local idx="$1"
    local start="$2"
    local end="$3"
    local expected_size="$4"
    local part_path="${PART_DIR}/part_${idx}"
    local tmp_path="${part_path}.tmp"

    if [[ -f "${part_path}" ]]; then
        local existing_size
        existing_size="$(wc -c < "${part_path}")"
        if [[ "${existing_size}" == "${expected_size}" ]]; then
            echo "part_${idx}: already complete (${existing_size} bytes)"
            return 0
        fi
    fi

    echo "part_${idx}: downloading bytes ${start}-${end}"
    curl -L --fail --show-error --silent -r "${start}-${end}" -o "${tmp_path}" "${URL}"

    local actual_size
    actual_size="$(wc -c < "${tmp_path}")"
    if [[ "${actual_size}" != "${expected_size}" ]]; then
        echo "part_${idx}: size mismatch ${actual_size}, expected ${expected_size}" >&2
        return 2
    fi
    mv "${tmp_path}" "${part_path}"
}

base_size=$((EXPECTED_BYTES / SEGMENTS))
last_index=$((SEGMENTS - 1))

pids=()
for i in $(seq 0 "${last_index}"); do
    start=$((i * base_size))
    if [[ "${i}" == "${last_index}" ]]; then
        end=$((EXPECTED_BYTES - 1))
    else
        end=$(((i + 1) * base_size - 1))
    fi
    expected_size=$((end - start + 1))
    idx="$(printf "%02d" "${i}")"
    download_part "${idx}" "${start}" "${end}" "${expected_size}" &
    pids+=("$!")
done

for pid in "${pids[@]}"; do
    wait "${pid}"
done

echo "Combining parts..."
: > "${TMP_TAR}"
for i in $(seq 0 "${last_index}"); do
    idx="$(printf "%02d" "${i}")"
    cat "${PART_DIR}/part_${idx}" >> "${TMP_TAR}"
done

actual_bytes="$(wc -c < "${TMP_TAR}")"
if [[ "${actual_bytes}" != "${EXPECTED_BYTES}" ]]; then
    echo "combined archive size mismatch ${actual_bytes}, expected ${EXPECTED_BYTES}" >&2
    exit 3
fi

mv "${TMP_TAR}" "${TAR_PATH}"
echo "downloaded=${TAR_PATH}"
echo "bytes=${actual_bytes}"
