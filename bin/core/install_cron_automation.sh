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
CHAIN_MODE="${BIZZAL_AUTOMATION_CHAIN_MODE:-single}"
SHADOWDARK_OFFSET_MIN="${BIZZAL_AUTOMATION_SHADOWDARK_OFFSET_MIN:-30}"

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

awk '
  BEGIN { skip=0 }
  /^[[:space:]]*# BEGIN BIZZAL_AUTOMATION[[:space:]]*\r?$/ { skip=1; next }
  /^[[:space:]]*# END BIZZAL_AUTOMATION[[:space:]]*\r?$/ { skip=0; next }
  !skip { print }
' "$TMP_CURR" > "$TMP_NEXT"

# Active systems, queried from the DB (replaces hardcoded dnd/shadowdark).
mapfile -t ACTIVE_SYSTEMS < <(cd "$REPO_ROOT" && python3 - <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
for sid in system_config.list_active_system_ids():
    print(sid)
PYEOF
)
if [[ ${#ACTIVE_SYSTEMS[@]} -eq 0 ]]; then
  echo "ERROR: no active rpg_systems rows found in the DB" >&2
  exit 1
fi
PRIMARY_SYSTEM="${ACTIVE_SYSTEMS[0]}"

{
  echo "$BEGIN_MARK"
  echo "# Local-time automation timezone"
  echo "CRON_TZ=$CRON_TZ_NAME"
  echo "BIZZAL_ENV_FILE=$HOME/.config/bizzal.env"
  echo "# Daily content pipeline with diagnostics (mode: $CHAIN_MODE, active systems: ${ACTIVE_SYSTEMS[*]})"
  if [[ "$CHAIN_MODE" == "dual" ]]; then
    OFFSET=0
    for sid in "${ACTIVE_SYSTEMS[@]}"; do
      echo "$((DAILY_MIN + OFFSET)) $DAILY_HOUR * * * cd $REPO_ROOT && set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/run_daily_diag_for_system.sh $sid"
      OFFSET=$((OFFSET + SHADOWDARK_OFFSET_MIN))
    done
  elif [[ "$CHAIN_MODE" == "alternating" ]]; then
    echo "$DAILY_MIN $DAILY_HOUR * * * cd $REPO_ROOT && set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/run_daily_diag_alternating_cron.sh"
  else
    echo "$DAILY_MIN $DAILY_HOUR * * * cd $REPO_ROOT && set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/run_daily_diag_for_system.sh $PRIMARY_SYSTEM"
  fi
  echo "# Weekly log pruning"
  echo "$WEEKLY_MIN $WEEKLY_HOUR * * $WEEKLY_DAY cd $REPO_ROOT && set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/prune_daily_diag_logs.sh --keep-days 30"
  echo "# Weekly YouTube auth probe with Discord alert on failures"
  echo "$WEEKLY_MIN $WEEKLY_HOUR * * $WEEKLY_DAY cd $REPO_ROOT && set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/youtube_auth_probe_discord.py >> $REPO_ROOT/logs/cron_youtube_auth_probe.log 2>&1"
  if [[ "$CHAIN_MODE" == "dual" || "$CHAIN_MODE" == "alternating" ]]; then
    for sid in "${ACTIVE_SYSTEMS[@]}"; do
      echo "# $sid Discord approval processing (every 5 minutes)"
      echo "*/5 * * * * cd $REPO_ROOT && set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/discord_publish_gate_for_system.sh $sid check --publish >> $REPO_ROOT/logs/cron_discord_publish_gate_$sid.log 2>&1"
    done
  else
    echo "# Discord approval processing (every 5 minutes)"
    echo "*/5 * * * * cd $REPO_ROOT && set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/discord_publish_gate_for_system.sh $PRIMARY_SYSTEM check --publish >> $REPO_ROOT/logs/cron_discord_publish_gate.log 2>&1"
  fi
  for sid in "${ACTIVE_SYSTEMS[@]}"; do
    echo "# $sid monthly longform approval processing (every 5 minutes)"
    echo "*/5 * * * * cd $REPO_ROOT && [ -f $REPO_ROOT/.venv/bin/activate ] && . $REPO_ROOT/.venv/bin/activate; set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/monthly_publish_gate_for_system.sh $sid check --publish >> $REPO_ROOT/logs/cron_monthly_publish_gate_$sid.log 2>&1"
    echo "# $sid monthly release bundle for previous month"
    echo "$MONTHLY_MIN $MONTHLY_HOUR $MONTHLY_DAY * * cd $REPO_ROOT && [ -f $REPO_ROOT/.venv/bin/activate ] && . $REPO_ROOT/.venv/bin/activate; set -a; [ -f \"\$BIZZAL_ENV_FILE\" ] && . \"\$BIZZAL_ENV_FILE\"; set +a; bin/core/monthly_release_for_system_cron.sh $sid \"\$(date -d 'last month' +\\%Y-\\%m)\" && bin/core/monthly_publish_gate_for_system.sh $sid request --month \"\$(date -d 'last month' +\\%Y-\\%m)\""
  done
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
