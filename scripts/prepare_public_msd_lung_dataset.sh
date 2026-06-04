#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-public_data/msd_task06_lung}"
URL="https://msd-for-monai.s3-us-west-2.amazonaws.com/Task06_Lung.tar"
EXPECTED_BYTES="9163696640"
TAR_PATH="${ROOT}/Task06_Lung.tar"
EXTRACT_DIR="${ROOT}/extracted"
MANIFEST="${ROOT}/manifest.txt"
SUMMARY="${ROOT}/download_validation_summary.txt"

mkdir -p "${ROOT}" "${EXTRACT_DIR}"

echo "Downloading/resuming MSD Task06 Lung..."
echo "URL: ${URL}"
echo "Target: ${TAR_PATH}"
curl -L -C - --fail --show-error -o "${TAR_PATH}" "${URL}"

actual_bytes="$(wc -c < "${TAR_PATH}")"
if [[ "${actual_bytes}" != "${EXPECTED_BYTES}" ]]; then
    echo "ERROR: unexpected file size: ${actual_bytes}; expected ${EXPECTED_BYTES}" >&2
    exit 2
fi

echo "Listing tar contents..."
tar -tf "${TAR_PATH}" > "${MANIFEST}"

if ! grep -q '^Task06_Lung/dataset.json$' "${MANIFEST}"; then
    echo "ERROR: dataset.json not found in tar archive" >&2
    exit 3
fi

echo "Extracting archive..."
tar -xf "${TAR_PATH}" -C "${EXTRACT_DIR}"

DATASET_DIR="${EXTRACT_DIR}/Task06_Lung"
images_tr="$(find "${DATASET_DIR}/imagesTr" -maxdepth 1 -type f -name '*.nii.gz' | wc -l)"
labels_tr="$(find "${DATASET_DIR}/labelsTr" -maxdepth 1 -type f -name '*.nii.gz' | wc -l)"
images_ts="$(find "${DATASET_DIR}/imagesTs" -maxdepth 1 -type f -name '*.nii.gz' | wc -l)"

{
    echo "dataset=MSD Task06 Lung"
    echo "source_url=${URL}"
    echo "tar_path=${TAR_PATH}"
    echo "expected_bytes=${EXPECTED_BYTES}"
    echo "actual_bytes=${actual_bytes}"
    echo "extract_dir=${DATASET_DIR}"
    echo "imagesTr=${images_tr}"
    echo "labelsTr=${labels_tr}"
    echo "imagesTs=${images_ts}"
    echo "status=ok"
} > "${SUMMARY}"

cat "${SUMMARY}"
