#!/usr/bin/env bash
# Shorts-from-long-form: turn a just-published long-form into 2-3 native Shorts
# ("clips") that funnel viewers to the full video.
#
# Runs as its OWN workflow step (not inside run_longform_for_system.sh) so it
# does NOT inherit the long-form render env (BIZZAL_SHORTS_DURATION=600,
# ENABLE_BODY_TEXT=0, per_screen art, etc.). Clips render with clean Shorts
# defaults: burned body text (sound-off), single bg image, ~30-45s.
#
# Usage: run_clips_for_system.sh <system_id> [day]
set -u

SYSTEM_ID="${1:?Usage: run_clips_for_system.sh <system_id> [day]}"
DAY="${2:-$(date +%F)}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

LOG_DIR="${BIZZAL_CLIPS_LOG_DIR:-$REPO_ROOT/logs/clips/$SYSTEM_ID}"
mkdir -p "$LOG_DIR"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR%/}/clips_${RUN_TS}.log"

# Resolve the source long-form video id from its registry (latest entry for DAY)
# so each clip's description can link back to the full video.
LF_REG="$REPO_ROOT/data/state/published_registry_longform_${SYSTEM_ID}.json"
VIDEO_ID=""
if [[ -f "$LF_REG" ]]; then
  VIDEO_ID="$(python3 - "$LF_REG" "$DAY" <<'PY'
import json, sys
try:
    items = json.load(open(sys.argv[1])).get("items", [])
    m = [i for i in items if i.get("day") == sys.argv[2] and i.get("youtube_video_id")]
    print(m[-1]["youtube_video_id"] if m else "")
except Exception:
    print("")
PY
)"
fi

run_inner() {
  set -e
  source "$REPO_ROOT/bin/core/system_env.sh" "$SYSTEM_ID"

  # Clip-specific state + render dirs (override AFTER system_env.sh, isolated
  # from both the daily Shorts and the long-form pipelines).
  export BIZZAL_PUBLISH_REGISTRY="data/state/published_registry_clips_${SYSTEM_ID}.json"
  export BIZZAL_STYLE_HISTORY_PATH="data/state/style_history_clips_${SYSTEM_ID}.json"
  export BIZZAL_ATOM_VALIDATED_DIR="data/atoms_clips_${SYSTEM_ID}/validated"
  export BIZZAL_RENDERS_BY_DAY_DIR="data/renders_clips_${SYSTEM_ID}/by_day"
  export BIZZAL_RENDERS_LATEST_DIR="data/renders_clips_${SYSTEM_ID}/latest"
  export BIZZAL_RENDERS_TMP_DIR="data/renders_clips_${SYSTEM_ID}/tmp"
  export BIZZAL_CONTENT_TYPE=clip
  mkdir -p "$REPO_ROOT/$BIZZAL_ATOM_VALIDATED_DIR" "$REPO_ROOT/data/state"

  echo "[run_clips:$SYSTEM_ID] generating clips (day=$DAY, source_video=${VIDEO_ID:-none})..."
  BIZZAL_SYSTEM_ID="$SYSTEM_ID" \
  BIZZAL_LONGFORM_DAY="$DAY" \
  BIZZAL_LONGFORM_VIDEO_ID="$VIDEO_ID" \
    python3 "$REPO_ROOT/bin/longform/make_clips_from_longform.py"

  local manifest="$REPO_ROOT/$BIZZAL_ATOM_VALIDATED_DIR/${DAY}.manifest.json"
  if [[ ! -f "$manifest" ]]; then
    echo "[run_clips:$SYSTEM_ID] no clip manifest; nothing to render"
    return 0
  fi

  local clip_days
  clip_days="$(python3 -c "import json,sys; print(' '.join(json.load(open(sys.argv[1])).get('clips',[])))" "$manifest")"
  if [[ -z "$clip_days" ]]; then
    echo "[run_clips:$SYSTEM_ID] manifest empty; nothing to render"
    return 0
  fi

  local clip_day _rc
  for clip_day in $clip_days; do
    echo "[run_clips:$SYSTEM_ID] === render clip ${clip_day} ==="
    _rc=0
    set +e
    "$REPO_ROOT/bin/render/render_atom.sh" "$clip_day"
    _rc=$?
    set -e
    if [[ $_rc -eq 20 ]]; then
      echo "[run_clips:$SYSTEM_ID] QUALITY GATE: ${clip_day} art/music missing; skipping"
      continue
    elif [[ $_rc -ne 0 ]]; then
      echo "[run_clips:$SYSTEM_ID] ${clip_day} render failed (rc=$_rc); skipping"
      continue
    fi

    if [[ "${BIZZAL_SKIP_PUBLISH:-0}" == "1" ]]; then
      echo "[run_clips:$SYSTEM_ID] SKIP_PUBLISH=1; not uploading ${clip_day}"
      continue
    fi

    python3 "$REPO_ROOT/bin/upload/upload_youtube.py" --day "$clip_day" \
      --category-id 20 --not-made-for-kids \
      || echo "[run_clips:$SYSTEM_ID] ${clip_day} upload failed (non-fatal)"
  done
}

{
  echo "[run_clips:$SYSTEM_ID] start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ) day=$DAY"
  if run_inner; then
    echo "[run_clips:$SYSTEM_ID] status=success"
  else
    echo "[run_clips:$SYSTEM_ID] status=failure rc=$?"
  fi
  echo "[run_clips:$SYSTEM_ID] end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} 2>&1 | tee "$LOG_FILE"
# Never fail the workflow: the long-form already published; clips are a bonus.
exit 0
