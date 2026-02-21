#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

LOG_DIR="${BIZZAL_DAILY_LOG_DIR:-/tmp}"
DAY="$(date +%F)"
LOG_FILE="${LOG_DIR%/}/bizzal_daily_${DAY}.log"

if [[ "${BIZZAL_PREVENT_SAME_DAY_RERUN:-1}" == "1" && -f "$LOG_FILE" ]]; then
  if grep -q "\[run_daily\] DONE" "$LOG_FILE"; then
    echo "[run_daily_diag] SKIP: successful run already exists for day=$DAY log=$LOG_FILE"
    echo "[run_daily_diag] Set BIZZAL_PREVENT_SAME_DAY_RERUN=0 only when you intentionally want a rerun."
    exit 0
  fi
fi

mkdir -p "$LOG_DIR"

# Activate venv if available
if [[ -f "$REPO/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
fi

# Load optional env file used for AI secrets
if [[ -f "$REPO/.env.ai" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO/.env.ai"
  set +a
fi

# Default diagnostics profile (caller can override before invoking)
export DEBUG_RENDER="${DEBUG_RENDER:-1}"
export BIZZAL_AI_DIAG="${BIZZAL_AI_DIAG:-1}"
export BIZZAL_ENABLE_AI="${BIZZAL_ENABLE_AI:-1}"
export BIZZAL_ENABLE_AI_SCRIPT="${BIZZAL_ENABLE_AI_SCRIPT:-1}"
export BIZZAL_ENABLE_PDF_FLAVOR="${BIZZAL_ENABLE_PDF_FLAVOR:-1}"
export BIZZAL_REQUIRE_PDF_FLAVOR="${BIZZAL_REQUIRE_PDF_FLAVOR:-0}"

echo "[run_daily_diag] repo=$REPO"
echo "[run_daily_diag] day=$DAY"
echo "[run_daily_diag] log=$LOG_FILE"
echo "[run_daily_diag] pdf_flavor=${BIZZAL_ENABLE_PDF_FLAVOR}"
echo "[run_daily_diag] require_pdf_flavor=${BIZZAL_REQUIRE_PDF_FLAVOR}"

"$REPO/bin/core/run_daily.sh" 2>&1 | tee "$LOG_FILE"

if [[ "${BIZZAL_REQUIRE_DISCORD_APPROVAL:-0}" == "1" ]]; then
  if [[ -x "$REPO/bin/core/discord_publish_gate.py" ]]; then
    if ! "$REPO/bin/core/discord_publish_gate.py" request --day "$DAY" 2>&1 | tee -a "$LOG_FILE"; then
      echo "[run_daily_diag] WARN: Discord approval request failed; keeping run successful" | tee -a "$LOG_FILE"
    fi
  else
    echo "[run_daily_diag] WARN: discord_publish_gate.py missing; cannot request approval" | tee -a "$LOG_FILE"
  fi
fi

echo "[run_daily_diag] --- diagnostics tail ---"
grep -E "AI script polish|AI CTA polish|PDF flavor|Encounter hook replaced|Encounter CTA replaced|category|angle|name" "$LOG_FILE" | tail -n 60 || true

SANITY_NOTIFY_DISCORD="${BIZZAL_DAILY_SANITY_NOTIFY_DISCORD:-1}"
SANITY_STRICT="${BIZZAL_DAILY_SANITY_STRICT:-0}"
SANITY_ARGS=(--day "$DAY" --log "$LOG_FILE")
if [[ "$SANITY_NOTIFY_DISCORD" == "1" ]]; then
  SANITY_ARGS+=(--notify-discord)
fi
if [[ "$SANITY_STRICT" == "1" ]]; then
  SANITY_ARGS+=(--strict)
fi

if [[ -x "$REPO/bin/core/daily_run_sanity.py" ]]; then
  if ! "$REPO/bin/core/daily_run_sanity.py" "${SANITY_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"; then
    echo "[run_daily_diag] WARN: daily sanity check returned non-zero" | tee -a "$LOG_FILE"
  fi
else
  echo "[run_daily_diag] WARN: daily_run_sanity.py missing; skipped" | tee -a "$LOG_FILE"
fi

echo "[run_daily_diag] done"
