#!/usr/bin/env bash
# Rotates through all active rpg_systems (per the DB), one per day, instead
# of a hardcoded two-way D&D/Shadowdark day-of-month-parity branch. Adding a
# system to the rotation is now a DB row change (is_active=true), not a code
# change here.
set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.venv/bin/activate"
fi

ENV_FILE="${BIZZAL_ENV_FILE:-$HOME/.config/bizzal.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

DAY_OF_YEAR="$(date +%j)"
SYSTEM_ID="$(python3 - "$DAY_OF_YEAR" <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
systems = system_config.list_active_system_ids()
if not systems:
    sys.exit("ERROR: no active rpg_systems rows found")
day_of_year = int(sys.argv[1])
print(systems[day_of_year % len(systems)])
PYEOF
)" || exit 1

exec "$REPO_ROOT/bin/core/run_daily_diag_for_system.sh" "$SYSTEM_ID"
