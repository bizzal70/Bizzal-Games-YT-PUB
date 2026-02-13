#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="${BIZZAL_DAILY_CRON_LOG_DIR:-$REPO_ROOT/logs}"
KEEP_DAYS="30"
DRY_RUN="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --log-dir)
      LOG_DIR="${2:-$LOG_DIR}"
      shift 2
      ;;
    --keep-days)
      KEEP_DAYS="${2:-$KEEP_DAYS}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    *)
      echo "usage: bin/core/prune_daily_diag_logs.sh [--log-dir PATH] [--keep-days N] [--dry-run]" >&2
      exit 2
      ;;
  esac
done

if [[ "$LOG_DIR" != /* ]]; then
  LOG_DIR="$REPO_ROOT/$LOG_DIR"
fi

if ! [[ "$KEEP_DAYS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --keep-days must be an integer >= 0" >&2
  exit 2
fi

if [[ ! -d "$LOG_DIR" ]]; then
  echo "[prune_daily_diag_logs] log dir missing, nothing to do: $LOG_DIR"
  exit 0
fi

mapfile -t LOGS < <(find "$LOG_DIR" -maxdepth 1 -type f -name 'daily_diag_*.log' -mtime +"$KEEP_DAYS" -print | sort)
COUNT="${#LOGS[@]}"

echo "[prune_daily_diag_logs] log_dir=$LOG_DIR keep_days=$KEEP_DAYS dry_run=$DRY_RUN matches=$COUNT"

if (( COUNT == 0 )); then
  echo "[prune_daily_diag_logs] nothing to prune"
  exit 0
fi

for f in "${LOGS[@]}"; do
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[prune_daily_diag_logs] would_remove=$f"
  else
    rm -f "$f"
    echo "[prune_daily_diag_logs] removed=$f"
  fi
done

echo "[prune_daily_diag_logs] pruned=$COUNT"
