#!/usr/bin/env bash
# Generic replacement for run_daily_diag_{dnd,shadowdark}.sh and their
# *_cron.sh variants. Cron-safe: timestamped log file, preserves exit code.
#
# Usage: run_daily_diag_for_system.sh <system_id>
set -u

SYSTEM_ID="${1:?Usage: run_daily_diag_for_system.sh <system_id>}"
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

LOG_DIR="${BIZZAL_DAILY_CRON_LOG_DIR:-$REPO_ROOT/logs/$SYSTEM_ID}"
mkdir -p "$LOG_DIR"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR%/}/daily_diag_${RUN_TS}.log"

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

run_inner() {
  set -e
  # shellcheck disable=SC1091
  source "$REPO_ROOT/bin/core/system_env.sh" "$SYSTEM_ID"
  export BIZZAL_DAILY_LOG_DIR="$LOG_DIR"
  export BIZZAL_REQUIRE_DISCORD_APPROVAL="${BIZZAL_REQUIRE_DISCORD_APPROVAL:-1}"
  export BIZZAL_DAILY_SANITY_STRICT="${BIZZAL_DAILY_SANITY_STRICT:-1}"
  "$REPO_ROOT/bin/core/run_daily_diag.sh"
}

{
  echo "[run_daily_diag_for_system:$SYSTEM_ID] start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[run_daily_diag_for_system:$SYSTEM_ID] repo=$REPO_ROOT"
  echo "[run_daily_diag_for_system:$SYSTEM_ID] log_file=$LOG_FILE"
  echo "[run_daily_diag_for_system:$SYSTEM_ID] env_file=$ENV_FILE"

  if run_inner; then
    echo "[run_daily_diag_for_system:$SYSTEM_ID] status=success"
    echo "[run_daily_diag_for_system:$SYSTEM_ID] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
  else
    code=$?
    echo "[run_daily_diag_for_system:$SYSTEM_ID] status=failure exit_code=$code"
    echo "[run_daily_diag_for_system:$SYSTEM_ID] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit "$code"
  fi
} >>"$LOG_FILE" 2>&1
