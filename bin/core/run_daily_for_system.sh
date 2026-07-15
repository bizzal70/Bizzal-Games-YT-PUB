#!/usr/bin/env bash
# Cloud (straight-through) daily runner: generate + render + publish in one
# pass, with NO Discord approval step. This is the sibling of
# run_daily_diag_for_system.sh (which keeps the human Discord gate for local
# use). Intended to run on GitHub Actions, but works anywhere the runtime is
# installed.
#
# Usage: run_daily_for_system.sh <system_id>
set -u

SYSTEM_ID="${1:?Usage: run_daily_for_system.sh <system_id>}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

LOG_DIR="${BIZZAL_DAILY_CRON_LOG_DIR:-$REPO_ROOT/logs/$SYSTEM_ID}"
mkdir -p "$LOG_DIR"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR%/}/daily_cloud_${RUN_TS}.log"

# Activate a local venv if present (no-op in CI, which installs into the runner).
if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.venv/bin/activate"
fi

# Optional env file (used locally; in CI everything comes from the environment).
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

  # Persist the publish-safety state in committed, version-controlled files
  # (data/state/) instead of the gitignored runtime/ + data/archive/ paths
  # system_env.sh defaults to. This is what lets GitHub Actions carry the
  # dedup registry + variety history across otherwise-ephemeral runs by
  # committing them back to the repo.
  local state_dir="$REPO_ROOT/data/state"
  mkdir -p "$state_dir"
  export BIZZAL_PUBLISH_REGISTRY="data/state/published_registry_${SYSTEM_ID}.json"
  export BIZZAL_STYLE_HISTORY_PATH="data/state/style_history_${SYSTEM_ID}.json"

  export BIZZAL_DAILY_LOG_DIR="$LOG_DIR"

  local day
  day="$(date +%F)"

  echo "[run_daily_for_system:$SYSTEM_ID] generate+render (day=$day)..."
  local _render_rc=0
  set +e
  "$REPO_ROOT/bin/core/run_daily.sh"
  _render_rc=$?
  set -e
  if [[ $_render_rc -eq 20 ]]; then
    echo "[run_daily_for_system:$SYSTEM_ID] QUALITY GATE: Replicate components missing; skipping publish (will retry next run)"
    return 0
  elif [[ $_render_rc -ne 0 ]]; then
    echo "[run_daily_for_system:$SYSTEM_ID] generate+render failed (rc=$_render_rc)"
    return $_render_rc
  fi

  if [[ "${BIZZAL_SKIP_PUBLISH:-0}" == "1" ]]; then
    echo "[run_daily_for_system:$SYSTEM_ID] BIZZAL_SKIP_PUBLISH=1; skipping autopublish (dry run)"
    return 0
  fi

  echo "[run_daily_for_system:$SYSTEM_ID] publish YouTube (day=$day)..."
  python "$REPO_ROOT/bin/upload/upload_youtube.py" --day "$day"

  if [[ -n "${BIZZAL_IG_ACCESS_TOKEN:-}" ]]; then
    echo "[run_daily_for_system:$SYSTEM_ID] publish Instagram (day=$day)..."
    python "$REPO_ROOT/bin/upload/upload_instagram.py" --day "$day"
  else
    echo "[run_daily_for_system:$SYSTEM_ID] BIZZAL_IG_ACCESS_TOKEN not set; skipping Instagram"
  fi
}

{
  echo "[run_daily_for_system:$SYSTEM_ID] start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[run_daily_for_system:$SYSTEM_ID] repo=$REPO_ROOT"
  echo "[run_daily_for_system:$SYSTEM_ID] log_file=$LOG_FILE"

  if run_inner; then
    echo "[run_daily_for_system:$SYSTEM_ID] status=success"
    echo "[run_daily_for_system:$SYSTEM_ID] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
  else
    code=$?
    echo "[run_daily_for_system:$SYSTEM_ID] status=failure exit_code=$code"
    echo "[run_daily_for_system:$SYSTEM_ID] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit "$code"
  fi
} 2>&1 | tee "$LOG_FILE"
exit "${PIPESTATUS[0]}"
