#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

LOG_DIR="${BIZZAL_DAILY_LOG_DIR:-/tmp}"
DAY="$(date +%F)"
LOG_FILE="${LOG_DIR%/}/bizzal_daily_${DAY}.log"

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
export BIZZAL_REQUIRE_PDF_FLAVOR="${BIZZAL_REQUIRE_PDF_FLAVOR:-1}"

echo "[run_daily_diag] repo=$REPO"
echo "[run_daily_diag] day=$DAY"
echo "[run_daily_diag] log=$LOG_FILE"
echo "[run_daily_diag] pdf_flavor=${BIZZAL_ENABLE_PDF_FLAVOR}"
echo "[run_daily_diag] require_pdf_flavor=${BIZZAL_REQUIRE_PDF_FLAVOR}"

"$REPO/bin/core/run_daily.sh" 2>&1 | tee "$LOG_FILE"

echo "[run_daily_diag] --- diagnostics tail ---"
grep -E "AI script polish|AI CTA polish|PDF flavor|Encounter hook replaced|Encounter CTA replaced|category|angle|name" "$LOG_FILE" | tail -n 60 || true
echo "[run_daily_diag] done"
