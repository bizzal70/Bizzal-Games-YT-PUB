#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${BIZZAL_ENV_FILE:-$HOME/.config/bizzal.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

missing=0

print_var_state() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "$value" ]]; then
    echo "${name}=SET(len=${#value})"
  else
    echo "${name}=MISSING"
    missing=1
  fi
}

echo "[preflight_prod_env] host=$(hostname) user=$(whoami)"
echo "[preflight_prod_env] repo=$REPO_ROOT"
echo "[preflight_prod_env] env_file=$ENV_FILE"
echo "[preflight_prod_env] approval_required=${BIZZAL_REQUIRE_DISCORD_APPROVAL:-0}"

if [[ "${BIZZAL_REQUIRE_DISCORD_APPROVAL:-0}" != "1" ]]; then
  echo "BIZZAL_REQUIRE_DISCORD_APPROVAL=MUST_BE_1"
  missing=1
fi

print_var_state BIZZAL_DISCORD_WEBHOOK_URL
print_var_state BIZZAL_DISCORD_BOT_TOKEN
print_var_state BIZZAL_DISCORD_CHANNEL_ID
print_var_state BIZZAL_DISCORD_APPROVER_USER_IDS

if [[ -n "${BIZZAL_PUBLISH_CMD:-}" ]]; then
  if [[ -x "${BIZZAL_PUBLISH_CMD}" ]]; then
    echo "BIZZAL_PUBLISH_CMD=OK"
  else
    echo "BIZZAL_PUBLISH_CMD=NOT_EXECUTABLE"
    missing=1
  fi
else
  echo "BIZZAL_PUBLISH_CMD=MISSING"
  missing=1
fi

if [[ "$missing" -eq 1 ]]; then
  echo "[preflight_prod_env] FAIL: missing/invalid required environment values"
  exit 2
fi

echo "[preflight_prod_env] PASS"
