#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT_DEFAULT="$(cd "$(dirname "$0")/../.." && pwd)"
REPO_ROOT="$REPO_ROOT_DEFAULT"
DRY_RUN="0"

# Scheduling defaults (local-time aware)
CRON_TZ_NAME="${BIZZAL_AUTOMATION_CRON_TZ:-America/Denver}"
DAILY_HOUR="${BIZZAL_AUTOMATION_DAILY_HOUR:-20}"
DAILY_MIN="${BIZZAL_AUTOMATION_DAILY_MIN:-0}"
WEEKLY_DAY="${BIZZAL_AUTOMATION_WEEKLY_DAY:-0}"
WEEKLY_HOUR="${BIZZAL_AUTOMATION_WEEKLY_HOUR:-20}"
WEEKLY_MIN="${BIZZAL_AUTOMATION_WEEKLY_MIN:-20}"
MONTHLY_DAY="${BIZZAL_AUTOMATION_MONTHLY_DAY:-1}"
MONTHLY_HOUR="${BIZZAL_AUTOMATION_MONTHLY_HOUR:-20}"
MONTHLY_MIN="${BIZZAL_AUTOMATION_MONTHLY_MIN:-10}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_ROOT="${2:-$REPO_ROOT}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    *)
      echo "usage: bin/core/install_cron_automation.sh [--repo PATH] [--dry-run]" >&2
      exit 2
      ;;
  esac
done

if [[ "$REPO_ROOT" != /* ]]; then
  REPO_ROOT="$PWD/$REPO_ROOT"
fi

if [[ ! -d "$REPO_ROOT" ]]; then
  echo "ERROR: repo path does not exist: $REPO_ROOT" >&2
  exit 2
fi

BEGIN_MARK="# BEGIN BIZZAL_AUTOMATION"
END_MARK="# END BIZZAL_AUTOMATION"

TMP_CURR="$(mktemp)"
TMP_NEXT="$(mktemp)"
trap 'rm -f "$TMP_CURR" "$TMP_NEXT"' EXIT

crontab -l > "$TMP_CURR" 2>/dev/null || true

awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
  $0 == begin {skip=1; next}
  $0 == end {skip=0; next}
  !skip {print}
' "$TMP_CURR" > "$TMP_NEXT"

{
  echo "$BEGIN_MARK"
  echo "# Local-time automation timezone"
  echo "CRON_TZ=$CRON_TZ_NAME"
  echo "# Daily content pipeline with diagnostics"
  echo "$DAILY_MIN $DAILY_HOUR * * * cd $REPO_ROOT && bin/core/run_daily_diag_cron.sh"
  echo "# Weekly log pruning"
  echo "$WEEKLY_MIN $WEEKLY_HOUR * * $WEEKLY_DAY cd $REPO_ROOT && bin/core/prune_daily_diag_logs.sh --keep-days 30"
  echo "# Discord approval processing (every 5 minutes)"
  echo "*/5 * * * * cd $REPO_ROOT && bin/core/discord_publish_gate.py check --publish >> $REPO_ROOT/logs/cron_discord_publish_gate.log 2>&1"
  echo "# Monthly release bundle for previous month"
  echo "$MONTHLY_MIN $MONTHLY_HOUR $MONTHLY_DAY * * cd $REPO_ROOT && bin/core/monthly_release_cron.sh \"\$(date -d 'last month' +\\%Y-\\%m)\""
  echo "$END_MARK"
} >> "$TMP_NEXT"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "[install_cron_automation] dry-run only; would install:" >&2
  cat "$TMP_NEXT"
  exit 0
fi

crontab "$TMP_NEXT"
echo "[install_cron_automation] installed automation cron block for repo: $REPO_ROOT"
echo "[install_cron_automation] current crontab:" >&2
crontab -l
