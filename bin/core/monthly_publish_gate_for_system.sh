#!/usr/bin/env bash
# Generic replacement for monthly_publish_gate_{dnd,shadowdark}.sh.
# Usage: monthly_publish_gate_for_system.sh <system_id> [args...]
set -euo pipefail

SYSTEM_ID="${1:?Usage: monthly_publish_gate_for_system.sh <system_id> [args...]}"
shift

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/bin/core/system_env.sh" "$SYSTEM_ID"

exec "$REPO_ROOT/bin/core/monthly_publish_gate.py" "$@"
