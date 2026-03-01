#!/usr/bin/env bash
set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

# Alternate by day parity: odd day -> D&D, even day -> Shadowdark
DAY_NUM="$(date +%d)"
if (( 10#$DAY_NUM % 2 == 0 )); then
  exec "$REPO_ROOT/bin/core/run_daily_diag_shadowdark_cron.sh"
else
  exec "$REPO_ROOT/bin/core/run_daily_diag_cron.sh"
fi
