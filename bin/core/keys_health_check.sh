#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HOME}/.config/bizzal.env"
PROBE=0

if [[ "${1:-}" == "--probe" ]]; then
  PROBE=1
fi

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

mask_secret() {
  local v="$1"
  local n=${#v}
  if (( n <= 10 )); then
    printf "%s" "(set)"
    return
  fi
  printf "%s...%s" "${v:0:6}" "${v: -4}"
}

show_var() {
  local k="$1"
  local mode="${2:-plain}"
  local v="${!k:-}"
  if [[ -z "$v" ]]; then
    echo "$k=MISSING"
    return
  fi
  if [[ "$mode" == "secret" ]]; then
    echo "$k=$(mask_secret "$v")"
  else
    echo "$k=$v"
  fi
}

echo "=== Bizzal Key Health Check ==="
show_var OPENAI_API_KEY secret
show_var REPLICATE_API_TOKEN secret
show_var BIZZAL_DISCORD_WEBHOOK_URL secret
show_var BIZZAL_DISCORD_BOT_TOKEN secret
show_var BIZZAL_DISCORD_CHANNEL_ID plain
show_var BIZZAL_DISCORD_APPROVER_USER_IDS plain
show_var BIZZAL_YT_CLIENT_SECRETS plain
show_var BIZZAL_YT_TOKEN_FILE plain
show_var BIZZAL_PUBLISH_CMD plain
show_var BIZZAL_ENABLE_AI plain
show_var BIZZAL_ENABLE_AI_SCRIPT plain

if [[ -n "${BIZZAL_YT_CLIENT_SECRETS:-}" && -f "${BIZZAL_YT_CLIENT_SECRETS}" ]]; then
  echo "YT_CLIENT_JSON=OK"
else
  echo "YT_CLIENT_JSON=MISSING"
fi

if [[ -n "${BIZZAL_PUBLISH_CMD:-}" && -x "${BIZZAL_PUBLISH_CMD}" ]]; then
  echo "PUBLISH_CMD=OK"
else
  echo "PUBLISH_CMD=NOT_EXECUTABLE_OR_MISSING"
fi

if [[ "$PROBE" != "1" ]]; then
  echo
  echo "Tip: run with --probe to test external auth endpoints."
  exit 0
fi

echo
echo "=== External Probe ==="

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  if curl -fsS -H "Authorization: Bearer ${OPENAI_API_KEY}" https://api.openai.com/v1/models >/dev/null; then
    echo "OPENAI_PROBE=OK"
  else
    echo "OPENAI_PROBE=FAIL"
  fi
else
  echo "OPENAI_PROBE=SKIP"
fi

if [[ -n "${REPLICATE_API_TOKEN:-}" ]]; then
  if curl -fsS -H "Authorization: Token ${REPLICATE_API_TOKEN}" https://api.replicate.com/v1/account >/dev/null; then
    echo "REPLICATE_PROBE=OK"
  else
    echo "REPLICATE_PROBE=FAIL"
  fi
else
  echo "REPLICATE_PROBE=SKIP"
fi

if [[ -n "${BIZZAL_DISCORD_WEBHOOK_URL:-}" ]]; then
  if curl -fsS -H "Content-Type: application/json" -d '{"content":"✅ bizzal webhook probe"}' "${BIZZAL_DISCORD_WEBHOOK_URL}" >/dev/null; then
    echo "DISCORD_WEBHOOK_PROBE=OK"
  else
    echo "DISCORD_WEBHOOK_PROBE=FAIL"
  fi
else
  echo "DISCORD_WEBHOOK_PROBE=SKIP"
fi

if [[ -n "${BIZZAL_YT_CLIENT_SECRETS:-}" && -f "${BIZZAL_YT_CLIENT_SECRETS}" ]]; then
  echo "YOUTUBE_CLIENT_FILE_PROBE=OK"
else
  echo "YOUTUBE_CLIENT_FILE_PROBE=FAIL"
fi
