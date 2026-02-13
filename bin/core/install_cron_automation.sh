#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT_DEFAULT="$(cd "$(dirname "$0")/../.." && pwd)"
REPO_ROOT="$REPO_ROOT_DEFAULT"
DRY_RUN="0"

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
  echo "# Daily content pipeline with diagnostics (09:00 UTC)"
  echo "0 9 * * * cd $REPO_ROOT && bin/core/run_daily_diag_cron.sh"
  echo "# Weekly log pruning (Sunday 09:20 UTC)"
  echo "20 9 * * 0 cd $REPO_ROOT && bin/core/prune_daily_diag_logs.sh --keep-days 30"
  echo "# Monthly release bundle for previous month (1st, 06:10 UTC)"
  echo "10 6 1 * * cd $REPO_ROOT && bin/core/monthly_release_cron.sh \"\$(date -d 'last month' +\\%Y-\\%m)\""
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
