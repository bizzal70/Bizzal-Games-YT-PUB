#!/usr/bin/env bash
set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

DAILY_LOG="logs/cron_run_daily.log"
MONTHLY_ROOT="data/archive/monthly"
MONTH_FILTER=""
DAILY_MARKER="\[run_daily\] DONE"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --month)
      MONTH_FILTER="${2:-}"
      shift 2
      ;;
    --daily-log)
      DAILY_LOG="${2:-$DAILY_LOG}"
      shift 2
      ;;
    *)
      echo "usage: bin/core/pipeline_health_check.sh [--month YYYY-MM] [--daily-log PATH]" >&2
      exit 2
      ;;
  esac
done

overall="GREEN"
daily_status="RED"
monthly_status="RED"
daily_detail="missing"
monthly_detail="missing"

# Daily health
# Fall back to current cron log conventions when legacy log is absent.
if [[ ! -f "$DAILY_LOG" && "$DAILY_LOG" == "logs/cron_run_daily.log" ]]; then
  latest_diag="$(find logs -maxdepth 1 -type f -name 'daily_diag_*.log' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2-)"
  if [[ -n "$latest_diag" && -f "$latest_diag" ]]; then
    DAILY_LOG="$latest_diag"
    DAILY_MARKER="\[run_daily_diag.*_cron\] status=success"
  else
    latest_daily="$(find logs -maxdepth 1 -type f -name 'bizzal_daily_*.log' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2-)"
    if [[ -n "$latest_daily" && -f "$latest_daily" ]]; then
      DAILY_LOG="$latest_daily"
      DAILY_MARKER="\[run_daily\] DONE"
    fi
  fi
fi

if [[ -f "$DAILY_LOG" ]]; then
  if tail -n 400 "$DAILY_LOG" | grep -q "$DAILY_MARKER"; then
    daily_status="GREEN"
    daily_detail="ok"
  else
    daily_detail="no_done_marker"
    overall="RED"
  fi
else
  daily_detail="missing_log"
  overall="RED"
fi

# Monthly health (latest log globally or within chosen month)
monthly_log=""
if [[ -d "$MONTHLY_ROOT" ]]; then
  if [[ -n "$MONTH_FILTER" ]]; then
    monthly_log="$(find "$MONTHLY_ROOT/$MONTH_FILTER/logs" -maxdepth 1 -type f -name 'monthly_release_*.log' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2-)"
  else
    monthly_log="$(find "$MONTHLY_ROOT" -type f -name 'monthly_release_*.log' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2-)"
  fi
fi

if [[ -n "$monthly_log" && -f "$monthly_log" ]]; then
  if grep -q "\[monthly_release_cron\] status=success" "$monthly_log" && grep -q "\[monthly_release\] DONE" "$monthly_log"; then
    monthly_status="GREEN"
    monthly_detail="ok"
  else
    monthly_detail="failed_or_incomplete"
    overall="RED"
  fi
else
  monthly_detail="missing_log"
  overall="RED"
fi

echo "PIPELINE_HEALTH ${overall} daily=${daily_status} monthly=${monthly_status} daily_log=${DAILY_LOG} daily_detail=${daily_detail} monthly_log=${monthly_log:-none} monthly_detail=${monthly_detail}"

if [[ "$overall" == "GREEN" ]]; then
  exit 0
fi
exit 1
