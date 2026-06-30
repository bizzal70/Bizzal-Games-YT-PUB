#!/usr/bin/env bash
# Cloud daily entrypoint (called by .github/workflows/daily.yml). Selects which
# active rpg_system(s) to run today, then runs the straight-through
# generate+render+publish path for each via run_daily_for_system.sh.
#
# System selection via BIZZAL_CLOUD_SYSTEMS:
#   (unset) | auto  -> rotate one system per day (day-of-year % count),
#                      matching the local alternating cron
#   all            -> run every active system today
#   "<id> [<id>..]" -> run exactly the listed system id(s)
set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.venv/bin/activate"
fi

SELECT="${BIZZAL_CLOUD_SYSTEMS:-auto}"

resolve_systems() {
  case "$SELECT" in
    all)
      python3 - <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
print(" ".join(system_config.list_active_system_ids()))
PYEOF
      ;;
    auto|"")
      python3 - "$(date +%j)" <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
systems = system_config.list_active_system_ids()
if not systems:
    sys.exit("ERROR: no active rpg_systems rows found")
print(systems[int(sys.argv[1]) % len(systems)])
PYEOF
      ;;
    *)
      # explicit id(s); normalise commas to spaces
      echo "${SELECT//,/ }"
      ;;
  esac
}

mapfile -t SYSTEMS < <(resolve_systems | tr ' ' '\n' | sed '/^$/d')
if [[ "${#SYSTEMS[@]}" -eq 0 ]]; then
  echo "[run_daily_cloud_cron] ERROR: no systems resolved (BIZZAL_CLOUD_SYSTEMS=$SELECT)" >&2
  exit 1
fi

echo "[run_daily_cloud_cron] systems=${SYSTEMS[*]} (select=$SELECT)"

rc_overall=0
for sys_id in "${SYSTEMS[@]}"; do
  echo "[run_daily_cloud_cron] === $sys_id ==="
  if "$REPO_ROOT/bin/core/run_daily_for_system.sh" "$sys_id"; then
    if [[ "${BIZZAL_ARCHIVE_RENDERS:-1}" == "1" ]]; then
      "$REPO_ROOT/bin/core/archive_render_to_storage.sh" "$sys_id" "$(date +%F)" || true
    fi
  else
    rc=$?
    echo "[run_daily_cloud_cron] system=$sys_id FAILED rc=$rc" >&2
    rc_overall=$rc
  fi
done

exit "$rc_overall"
