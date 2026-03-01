#!/usr/bin/env bash
set -u

PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

LOG_DIR="${BIZZAL_DAILY_CRON_LOG_DIR:-$REPO_ROOT/logs/shadowdark}"
mkdir -p "$LOG_DIR"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR%/}/daily_diag_shadowdark_${RUN_TS}.log"

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.venv/bin/activate"
fi

ENV_FILE="${BIZZAL_ENV_FILE:-$HOME/.config/bizzal.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

{
  echo "[run_daily_diag_shadowdark_cron] start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[run_daily_diag_shadowdark_cron] repo=$REPO_ROOT"
  echo "[run_daily_diag_shadowdark_cron] log_file=$LOG_FILE"
  echo "[run_daily_diag_shadowdark_cron] env_file=$ENV_FILE"

  if BIZZAL_DAILY_CRON_LOG_DIR="$LOG_DIR" "$REPO_ROOT/bin/core/run_daily_diag_shadowdark.sh"; then
    echo "[run_daily_diag_shadowdark_cron] status=success"
    echo "[run_daily_diag_shadowdark_cron] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
  else
    code=$?
    echo "[run_daily_diag_shadowdark_cron] status=failure exit_code=$code"
    echo "[run_daily_diag_shadowdark_cron] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit "$code"
  fi
} >>"$LOG_FILE" 2>&1
