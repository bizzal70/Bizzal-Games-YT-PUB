#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
	# shellcheck disable=SC1091
	source "$REPO_ROOT/.venv/bin/activate"
fi

DAYS=10
REQUEST_MISSING=0
CHAIN_MODE="all"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--days)
			DAYS="${2:-}"
			shift 2
			;;
		--request-missing)
			REQUEST_MISSING=1
			shift
			;;
		--chain)
			CHAIN_MODE="${2:-}"
			shift 2
			;;
		*)
			echo "usage: bin/core/recover_recent_publish_backlog.sh [--days N] [--request-missing] [--chain <system_id>|all]" >&2
			exit 2
			;;
	esac
done

if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || [[ "$DAYS" -lt 1 ]]; then
	echo "ERROR: --days must be a positive integer" >&2
	exit 2
fi

if [[ "$CHAIN_MODE" == "all" ]]; then
	mapfile -t CHAIN_SYSTEMS < <(python3 - <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
for sid in system_config.list_active_system_ids():
    print(sid)
PYEOF
	)
else
	CHAIN_SYSTEMS=("$CHAIN_MODE")
fi

resolve_path() {
	local raw="$1"
	if [[ "$raw" = /* ]]; then
		printf '%s\n' "$raw"
	else
		printf '%s\n' "$REPO_ROOT/$raw"
	fi
}

json_status() {
	local state_file="$1"
	local day="$2"
	if [[ ! -f "$state_file" ]]; then
		printf '\n'
		return 0
	fi
	jq -r --arg day "$day" '.approvals[$day].status // ""' "$state_file"
}

has_validated_atom() {
	local validated_dir="$1"
	local day="$2"
	[[ -f "$validated_dir/$day.json" ]]
}

run_chain() {
	local label="$1"
	local retried=0
	local requested=0
	local pending=0
	local missing=0

	# shellcheck disable=SC1091
	source "$REPO_ROOT/bin/core/system_env.sh" "$label"
	local gate_wrapper=("$REPO_ROOT/bin/core/discord_publish_gate_for_system.sh" "$label")

	local state_file
	state_file="$(resolve_path "$BIZZAL_DISCORD_APPROVAL_STATE")"
	local validated_dir
	validated_dir="$(resolve_path "$BIZZAL_ATOM_VALIDATED_DIR")"

	echo "[recover_backlog] chain=$label days=$DAYS request_missing=$REQUEST_MISSING"

	for ((offset=DAYS-1; offset>=0; offset--)); do
		local day
		day="$(date -d "$offset days ago" +%F)"
		local status
		status="$(json_status "$state_file" "$day")"

		case "$status" in
			published)
				echo "[recover_backlog] $label $day status=published skip"
				;;
			approved|approved_publish_failed)
				echo "[recover_backlog] $label $day status=$status retry"
				"${gate_wrapper[@]}" retry --day "$day"
				retried=$((retried + 1))
				;;
			pending)
				echo "[recover_backlog] $label $day status=pending awaiting_discord_approval"
				pending=$((pending + 1))
				;;
			rejected)
				echo "[recover_backlog] $label $day status=rejected skip"
				;;
			"")
				if has_validated_atom "$validated_dir" "$day"; then
					if [[ "$REQUEST_MISSING" == "1" ]]; then
						echo "[recover_backlog] $label $day status=missing request"
						"${gate_wrapper[@]}" request --day "$day"
						requested=$((requested + 1))
					else
						echo "[recover_backlog] $label $day status=missing validated_atom_present request_missing_disabled"
						missing=$((missing + 1))
					fi
				else
					echo "[recover_backlog] $label $day status=missing no_validated_atom"
				fi
				;;
			*)
				echo "[recover_backlog] $label $day status=$status skip"
				;;
		esac
	done

	echo "[recover_backlog] chain=$label retried=$retried requested=$requested pending=$pending missing=$missing"
}

for sid in "${CHAIN_SYSTEMS[@]}"; do
	run_chain "$sid"
done