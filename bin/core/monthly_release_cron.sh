#!/usr/bin/env bash
set -u

PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

MONTH="${1:-$(date +%Y-%m)}"
LOG_DIR="data/archive/monthly/${MONTH}/logs"
mkdir -p "$LOG_DIR"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR}/monthly_release_${RUN_TS}.log"

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.venv/bin/activate"
fi

{
  echo "[monthly_release_cron] start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[monthly_release_cron] repo=$REPO_ROOT"
  echo "[monthly_release_cron] month=$MONTH"

  if "$REPO_ROOT/bin/core/monthly_release_bundle.sh" "$MONTH"; then
    echo "[monthly_release_cron] status=success"
    echo "[monthly_release_cron] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
  else
    code=$?
    echo "[monthly_release_cron] status=failure exit_code=$code"
    echo "[monthly_release_cron] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit "$code"
  fi
} >>"$LOG_FILE" 2>&1
