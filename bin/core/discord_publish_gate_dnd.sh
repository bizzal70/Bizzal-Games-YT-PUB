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

exec "$REPO_ROOT/bin/core/discord_publish_gate.py" "$@"
