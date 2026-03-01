#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$REPO_ROOT/bin/core/shadowdark_env.sh"

export BIZZAL_DAILY_LOG_DIR="${BIZZAL_DAILY_LOG_DIR:-$REPO_ROOT/logs/shadowdark}"
export BIZZAL_REQUIRE_DISCORD_APPROVAL="${BIZZAL_REQUIRE_DISCORD_APPROVAL:-1}"
export BIZZAL_DAILY_SANITY_STRICT="${BIZZAL_DAILY_SANITY_STRICT:-1}"

"$REPO_ROOT/bin/core/run_daily_diag.sh"
