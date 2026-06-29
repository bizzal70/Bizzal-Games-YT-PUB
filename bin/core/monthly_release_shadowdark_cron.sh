#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/bin/core/shadowdark_env.sh"

export BIZZAL_MONTHLY_ROOT="${BIZZAL_SD_MONTHLY_ROOT:-data/archive/monthly/shadowdark}"
export BIZZAL_DISCORD_MONTHLY_APPROVAL_STATE="${BIZZAL_SD_DISCORD_MONTHLY_APPROVAL_STATE:-data/archive/approvals/discord_monthly_publish_gate_shadowdark.json}"
export BIZZAL_MONTHLY_PUBLISH_REGISTRY="${BIZZAL_SD_MONTHLY_PUBLISH_REGISTRY:-data/archive/publish/published_monthly_registry_shadowdark.json}"

exec "$REPO_ROOT/bin/core/monthly_release_cron.sh" "$@"
