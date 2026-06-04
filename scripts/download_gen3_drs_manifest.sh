#!/usr/bin/env bash
set -euo pipefail

MANIFEST="${1:?Usage: bash scripts/download_gen3_drs_manifest.sh <manifest.json> <out_dir>}"
OUT_DIR="${2:?Usage: bash scripts/download_gen3_drs_manifest.sh <manifest.json> <out_dir>}"
PROFILE="${GEN3_PROFILE:-nci-crdc}"
ENDPOINT="${GEN3_ENDPOINT:-https://nci-crdc.datacommons.io}"
CRED_JSON="${GEN3_CREDENTIALS_JSON:-}"

if ! command -v gen3 >/dev/null 2>&1; then
    cat >&2 <<'EOF'
ERROR: gen3 client is not installed.

Install and configure the Gen3 client after obtaining authorized dbGaP/CRDC access.
Recommended endpoint:
  https://nci-crdc.datacommons.io

Then rerun this script.
EOF
    exit 127
fi

if [[ ! -f "${MANIFEST}" ]]; then
    echo "ERROR: manifest not found: ${MANIFEST}" >&2
    exit 2
fi

mkdir -p "${OUT_DIR}"

if [[ -n "${CRED_JSON}" ]]; then
    if [[ ! -f "${CRED_JSON}" ]]; then
        echo "ERROR: GEN3_CREDENTIALS_JSON does not exist: ${CRED_JSON}" >&2
        exit 3
    fi
    gen3 configure --profile "${PROFILE}" --endpoint "${ENDPOINT}" --cred "${CRED_JSON}"
fi

gen3 drs-pull object --profile "${PROFILE}" --manifest "${MANIFEST}" --download-path "${OUT_DIR}"
