#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  RUN_NAME=name NOTIFY_NTFY_TOPIC=topic bash scripts/notify_on_completion.sh -- command [args...]

Common tmux form:
  tmux new-session -d -s name 'RUN_NAME=name NOTIFY_NTFY_TOPIC=topic bash scripts/notify_on_completion.sh -- bash <your_job_script>.sh'

Notification options:
  NOTIFY_NTFY_TOPIC   ntfy topic name, or a full ntfy topic URL
  NOTIFY_NTFY_SERVER  ntfy server URL, default: https://ntfy.sh
  NOTIFY_WEBHOOK_URL  generic webhook URL; message is sent as plain text
  NOTIFY_DRY_RUN=1    do not call remote endpoints; print intended notice

Output options:
  RUN_NAME            human-readable run name
  RUN_ID              stable run id; default uses timestamp and PID
  LOG_ROOT            default: logs/notified_runs
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ "${1:-}" == "--" ]]; then
    shift
fi

if [[ "$#" -eq 0 ]]; then
    usage >&2
    exit 2
fi

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_NAME="${RUN_NAME:-$1}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)_$$}"
LOG_ROOT="${LOG_ROOT:-${PROJECT_ROOT}/logs/notified_runs}"
RUN_DIR="${LOG_ROOT}/${RUN_ID}"
LOG_FILE="${RUN_DIR}/run.log"
STATUS_FILE="${RUN_DIR}/status.txt"
COMMAND_FILE="${RUN_DIR}/command.txt"

mkdir -p "${RUN_DIR}"
printf '%q ' "$@" > "${COMMAND_FILE}"
printf '\n' >> "${COMMAND_FILE}"

timestamp_utc() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

send_notice() {
    local status="$1"
    local exit_code="$2"
    local started_at="$3"
    local finished_at="$4"
    local host
    host="$(hostname 2>/dev/null || printf unknown-host)"

    local message
    message="${status}: ${RUN_NAME}
host: ${host}
exit_code: ${exit_code}
started_at: ${started_at}
finished_at: ${finished_at}
log: ${LOG_FILE}"

    if [[ "${NOTIFY_DRY_RUN:-0}" == "1" ]]; then
        printf '[notify dry-run]\n%s\n' "${message}" >&2
        return 0
    fi

    if [[ -n "${NOTIFY_WEBHOOK_URL:-}" ]]; then
        curl -fsS --max-time "${NOTIFY_TIMEOUT:-20}" \
            -H "Content-Type: text/plain; charset=utf-8" \
            --data-binary "${message}" \
            "${NOTIFY_WEBHOOK_URL}" >/dev/null
        return $?
    fi

    if [[ -n "${NOTIFY_NTFY_TOPIC:-}" ]]; then
        local topic_url
        if [[ "${NOTIFY_NTFY_TOPIC}" == http://* || "${NOTIFY_NTFY_TOPIC}" == https://* ]]; then
            topic_url="${NOTIFY_NTFY_TOPIC}"
        else
            topic_url="${NOTIFY_NTFY_SERVER:-https://ntfy.sh}/${NOTIFY_NTFY_TOPIC}"
        fi

        curl -fsS --max-time "${NOTIFY_TIMEOUT:-20}" \
            -H "Title: ${RUN_NAME}" \
            -H "Tags: computer" \
            --data-binary "${message}" \
            "${topic_url}" >/dev/null
        return $?
    fi

    printf '[notify skipped] set NOTIFY_NTFY_TOPIC or NOTIFY_WEBHOOK_URL for external notification\n' >&2
    return 0
}

STARTED_AT="$(timestamp_utc)"
{
    printf 'run_name=%s\n' "${RUN_NAME}"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'started_at=%s\n' "${STARTED_AT}"
    printf 'command='
    printf '%q ' "$@"
    printf '\n'
    printf 'log=%s\n' "${LOG_FILE}"
} > "${STATUS_FILE}"

set +e
(
    printf '[%s] START %s\n' "${STARTED_AT}" "${RUN_NAME}"
    printf 'Command: '
    printf '%q ' "$@"
    printf '\n\n'
    "$@"
) > "${LOG_FILE}" 2>&1
EXIT_CODE=$?
set -e

FINISHED_AT="$(timestamp_utc)"
if [[ "${EXIT_CODE}" -eq 0 ]]; then
    STATUS="DONE"
else
    STATUS="FAILED"
fi

{
    printf 'run_name=%s\n' "${RUN_NAME}"
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'status=%s\n' "${STATUS}"
    printf 'exit_code=%s\n' "${EXIT_CODE}"
    printf 'started_at=%s\n' "${STARTED_AT}"
    printf 'finished_at=%s\n' "${FINISHED_AT}"
    printf 'log=%s\n' "${LOG_FILE}"
} > "${STATUS_FILE}"

{
    printf '\n[%s] %s exit_code=%s\n' "${FINISHED_AT}" "${STATUS}" "${EXIT_CODE}"
} >> "${LOG_FILE}"

if ! send_notice "${STATUS}" "${EXIT_CODE}" "${STARTED_AT}" "${FINISHED_AT}" >> "${LOG_FILE}" 2>&1; then
    printf '[%s] notice delivery failed\n' "$(timestamp_utc)" >> "${LOG_FILE}"
fi

exit "${EXIT_CODE}"
