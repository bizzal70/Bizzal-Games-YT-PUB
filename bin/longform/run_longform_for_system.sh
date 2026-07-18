#!/usr/bin/env bash
# Long-form cloud runner: generate script + render + upload for one system.
# Mirrors run_daily_for_system.sh but for long-form content (8-10 min videos).
#
# Usage: run_longform_for_system.sh <system_id>
set -u

SYSTEM_ID="${1:?Usage: run_longform_for_system.sh <system_id>}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

LOG_DIR="${BIZZAL_LONGFORM_LOG_DIR:-$REPO_ROOT/logs/longform/$SYSTEM_ID}"
mkdir -p "$LOG_DIR"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR%/}/longform_cloud_${RUN_TS}.log"

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  . "$REPO_ROOT/.venv/bin/activate"
fi

ENV_FILE="${BIZZAL_ENV_FILE:-$HOME/.config/bizzal.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a; . "$ENV_FILE"; set +a
fi

run_inner() {
  set -e
  source "$REPO_ROOT/bin/core/system_env.sh" "$SYSTEM_ID"

  local state_dir="$REPO_ROOT/data/state"
  mkdir -p "$state_dir"

  # Long-form uses separate state files so it never collides with Shorts
  export BIZZAL_PUBLISH_REGISTRY="data/state/published_registry_longform_${SYSTEM_ID}.json"
  export BIZZAL_STYLE_HISTORY_PATH="data/state/style_history_longform_${SYSTEM_ID}.json"

  # Long-form atom + render paths (separate dirs from Shorts)
  export BIZZAL_ATOM_INCOMING_DIR="data/atoms_longform_${SYSTEM_ID}/incoming"
  export BIZZAL_ATOM_VALIDATED_DIR="data/atoms_longform_${SYSTEM_ID}/validated"
  export BIZZAL_ATOM_FAILED_DIR="data/atoms_longform_${SYSTEM_ID}/failed"
  export BIZZAL_RENDERS_BY_DAY_DIR="data/renders_longform_${SYSTEM_ID}/by_day"
  export BIZZAL_RENDERS_LATEST_DIR="data/renders_longform_${SYSTEM_ID}/latest"
  export BIZZAL_RENDERS_TMP_DIR="data/renders_longform_${SYSTEM_ID}/tmp"

  # Long-form video parameters
  export BIZZAL_SHORTS_DURATION=600       # 10 min max (render will be actual script length)

  # Pagination: the long-form body is ~800 words. The renderer's Shorts default
  # (5 lines/screen, capped at 4 pages) collapses that into 4 screens of ~40
  # lines each -- unreadable walls of text. Paginate into many short screens
  # (<=6 wrapped lines each), each with its own narration + art, instead.
  export BIZZAL_BODY_MAXLINES=6
  export BIZZAL_BODY_MAX_PAGES=60
  # Let the per-screen narration drive dwell time (low floor) so short screens
  # aren't padded out with dead air. A ~30-word screen narrates in ~12s; the
  # old 20s floor left ~8s of silence per screen across ~30 screens.
  export BIZZAL_BODY_PAGE_MIN_SEC=8
  export BIZZAL_TTS_BODY_PAGE_MIN_SEC=8
  export BIZZAL_END_FADE_SEC=2.0
  export BIZZAL_END_BLACK_PAD_SEC=1.0
  export BIZZAL_CONTENT_TYPE=longform

  export BIZZAL_LONGFORM_LOG_DIR="$LOG_DIR"

  local day
  day="$(date +%F)"

  echo "[run_longform_for_system:$SYSTEM_ID] make_longform_atom (day=$day)..."
  python3 "$REPO_ROOT/bin/longform/make_longform_atom.py" --day "$day"

  echo "[run_longform_for_system:$SYSTEM_ID] render..."
  "$REPO_ROOT/bin/render/render_atom.sh" "$day"

  if [[ "${BIZZAL_SKIP_PUBLISH:-0}" == "1" ]]; then
    echo "[run_longform_for_system:$SYSTEM_ID] BIZZAL_SKIP_PUBLISH=1; skipping upload (dry run)"
    return 0
  fi

  echo "[run_longform_for_system:$SYSTEM_ID] upload to YouTube..."
  python3 "$REPO_ROOT/bin/upload/upload_youtube.py" --day "$day" \
    --title-override "${BIZZAL_LONGFORM_YT_TITLE:-}" \
    --description-override "${BIZZAL_LONGFORM_YT_DESC:-}" \
    --category-id 20 \
    --not-made-for-kids || true

  echo "[run_longform_for_system:$SYSTEM_ID] archive render..."
  "$REPO_ROOT/bin/core/archive_render_to_storage.sh" "$SYSTEM_ID" "$day" || true
}

{
  echo "[run_longform_for_system:$SYSTEM_ID] start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[run_longform_for_system:$SYSTEM_ID] repo=$REPO_ROOT"
  echo "[run_longform_for_system:$SYSTEM_ID] log_file=$LOG_FILE"

  if run_inner; then
    echo "[run_longform_for_system:$SYSTEM_ID] status=success"
    echo "[run_longform_for_system:$SYSTEM_ID] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
  else
    code=$?
    echo "[run_longform_for_system:$SYSTEM_ID] status=failure exit_code=$code"
    echo "[run_longform_for_system:$SYSTEM_ID] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit "$code"
  fi
} 2>&1 | tee "$LOG_FILE"
exit "${PIPESTATUS[0]}"
