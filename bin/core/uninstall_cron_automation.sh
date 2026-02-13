#!/usr/bin/env bash
set -euo pipefail

DRY_RUN="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    *)
      echo "usage: bin/core/uninstall_cron_automation.sh [--dry-run]" >&2
      exit 2
      ;;
  esac
done

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

if cmp -s "$TMP_CURR" "$TMP_NEXT"; then
  echo "[uninstall_cron_automation] managed cron block not found; nothing to remove"
  exit 0
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "[uninstall_cron_automation] dry-run only; resulting crontab would be:" >&2
  cat "$TMP_NEXT"
  exit 0
fi

crontab "$TMP_NEXT"
echo "[uninstall_cron_automation] removed managed automation cron block"
echo "[uninstall_cron_automation] current crontab:" >&2
crontab -l
