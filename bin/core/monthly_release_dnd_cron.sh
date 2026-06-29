#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/bin/core/dnd_env.sh"

export BIZZAL_MONTHLY_ROOT="${BIZZAL_DND_MONTHLY_ROOT:-data/archive/monthly/dnd}"
export BIZZAL_DISCORD_MONTHLY_APPROVAL_STATE="${BIZZAL_DND_DISCORD_MONTHLY_APPROVAL_STATE:-data/archive/approvals/discord_monthly_publish_gate_dnd.json}"
export BIZZAL_MONTHLY_PUBLISH_REGISTRY="${BIZZAL_DND_MONTHLY_PUBLISH_REGISTRY:-data/archive/publish/published_monthly_registry_dnd.json}"

exec "$REPO_ROOT/bin/core/monthly_release_cron.sh" "$@"
