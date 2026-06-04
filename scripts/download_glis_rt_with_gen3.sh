#!/usr/bin/env bash
set -euo pipefail

MANIFEST="${1:-public_data/glis_rt/manifests/glis_rt_all_gen3_manifest.json}"
OUT_DIR="${2:-public_data/glis_rt/raw_zips}"

exec bash scripts/download_gen3_drs_manifest.sh "${MANIFEST}" "${OUT_DIR}"
