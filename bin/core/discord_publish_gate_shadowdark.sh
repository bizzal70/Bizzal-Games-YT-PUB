#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$REPO_ROOT/bin/core/shadowdark_env.sh"

exec "$REPO_ROOT/bin/core/discord_publish_gate.py" "$@"
