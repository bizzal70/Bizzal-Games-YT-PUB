#!/usr/bin/env bash
# recover_youtube_auth_and_backlog.sh
#
# Run this to:
#   1. Pull latest code from origin
#   2. Install/verify Python deps
#   3. Run preflight (includes YouTube auth probe)
#   4. If auth is OK, retry the D&D and Shadowdark backlog for the given days
#
# Usage:
#   bash bin/core/recover_youtube_auth_and_backlog.sh
#   bash bin/core/recover_youtube_auth_and_backlog.sh --days 2026-03-24 2026-03-25
#
# If preflight reports YOUTUBE_AUTH=INVALID_GRANT the script will stop and tell
# you exactly what to run interactively before re-running this script.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# -- Days to retry (default: 2026-03-24 and 2026-03-25) ---------------------
RETRY_DAYS=()
if [[ $# -gt 0 && "$1" == "--days" ]]; then
  shift
  while [[ $# -gt 0 ]]; do
    RETRY_DAYS+=("$1")
    shift
  done
fi
if [[ ${#RETRY_DAYS[@]} -eq 0 ]]; then
  RETRY_DAYS=(2026-03-24 2026-03-25)
fi

# ---------------------------------------------------------------------------
echo "================================================================"
echo " STEP 1: git pull"
echo "================================================================"
git fetch origin
git checkout main
git pull --rebase origin main

echo ""
echo "================================================================"
echo " STEP 2: Python deps"
echo "================================================================"
if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
fi
python3 -m pip install -q -r requirements.txt

echo ""
echo "================================================================"
echo " STEP 3: Preflight (includes YouTube auth probe)"
echo "================================================================"
set +e
bash bin/core/preflight_prod_env.sh
PREFLIGHT_RC=$?
set -e

if [[ "$PREFLIGHT_RC" -ne 0 ]]; then
  echo ""
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo " Preflight FAILED (rc=$PREFLIGHT_RC)."
  echo ""
  echo " If the output above shows:"
  echo "   YOUTUBE_AUTH=INVALID_GRANT"
  echo " then run this interactively to fix the token:"
  echo ""
  echo "   cd $REPO_ROOT"
  echo "   . .venv/bin/activate"
  echo "   bin/upload/upload_youtube.py --refresh-auth-only"
  echo ""
  echo " Follow the browser URL prompt, paste the code back, then"
  echo " re-run this script."
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  exit "$PREFLIGHT_RC"
fi

mapfile -t RECOVER_SYSTEMS < <(python3 - <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
for sid in system_config.list_active_system_ids():
    print(sid)
PYEOF
)

echo ""
echo "================================================================"
echo " STEP 4: Retry backlog for active systems: ${RECOVER_SYSTEMS[*]}"
echo "================================================================"
for SID in "${RECOVER_SYSTEMS[@]}"; do
  for DAY in "${RETRY_DAYS[@]}"; do
    echo "--- $SID retry day=$DAY"
    set +e
    bin/core/discord_publish_gate_for_system.sh "$SID" retry --day "$DAY"
    echo "  done (rc=$?)"
    set -e
  done
done

echo ""
echo "================================================================"
echo " STEP 5: Status check"
echo "================================================================"
for SID in "${RECOVER_SYSTEMS[@]}"; do
  echo "--- $SID ---"
  STATE_FILE="$(source bin/core/system_env.sh "$SID" >/dev/null && echo "$BIZZAL_DISCORD_APPROVAL_STATE")"
  jq '.approvals | to_entries[]
    | select(.key >= "2026-03-24")
    | {day:.key, status:.value.status, rc:.value.publish_rc, url:.value.youtube_url}' \
    "$STATE_FILE"
done

echo ""
echo "================================================================"
echo " Done. Check output above — all days should show status=published."
echo "================================================================"
