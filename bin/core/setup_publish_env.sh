#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HOME}/.config/bizzal.env"
BASHRC_FILE="${HOME}/.bashrc"

mkdir -p "$(dirname "$ENV_FILE")"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

echo "Bizzal Discord/Publish environment setup"
echo "Values will be saved to: $ENV_FILE"
echo

prompt_value() {
  local var_name="$1"
  local prompt_text="$2"
  local secret="${3:-0}"
  local current="${!var_name:-}"
  local input

  if [[ "$secret" == "1" ]]; then
    if [[ -n "$current" ]]; then
      read -r -s -p "$prompt_text [press Enter to keep current]: " input
    else
      read -r -s -p "$prompt_text: " input
    fi
    echo
  else
    if [[ -n "$current" ]]; then
      read -r -p "$prompt_text [$current]: " input
    else
      read -r -p "$prompt_text: " input
    fi
  fi

  if [[ -n "$input" ]]; then
    printf -v "$var_name" '%s' "$input"
  fi
}

prompt_value BIZZAL_DISCORD_WEBHOOK_URL "Discord webhook URL"
if [[ -n "${BIZZAL_DISCORD_WEBHOOK_URL:-}" && ${#BIZZAL_DISCORD_WEBHOOK_URL} -ge 2 ]]; then
  first="${BIZZAL_DISCORD_WEBHOOK_URL:0:1}"
  last="${BIZZAL_DISCORD_WEBHOOK_URL: -1}"
  if [[ "$first" == "$last" && ( "$first" == "'" || "$first" == '"' ) ]]; then
    BIZZAL_DISCORD_WEBHOOK_URL="${BIZZAL_DISCORD_WEBHOOK_URL:1:${#BIZZAL_DISCORD_WEBHOOK_URL}-2}"
  fi
fi
prompt_value BIZZAL_DISCORD_BOT_TOKEN "Discord bot token" 1
prompt_value BIZZAL_DISCORD_CHANNEL_ID "Discord channel ID"
prompt_value BIZZAL_DISCORD_APPROVER_USER_IDS "Approver user ID(s), comma-separated"
prompt_value BIZZAL_PUBLISH_CMD "Publish command (exact upload command)"

required=(
  BIZZAL_DISCORD_WEBHOOK_URL
  BIZZAL_DISCORD_BOT_TOKEN
  BIZZAL_DISCORD_CHANNEL_ID
  BIZZAL_DISCORD_APPROVER_USER_IDS
  BIZZAL_PUBLISH_CMD
)

for v in "${required[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: $v is empty. Re-run setup and provide all values." >&2
    exit 2
  fi
done

cat > "$ENV_FILE" <<EOF
export BIZZAL_DISCORD_WEBHOOK_URL='${BIZZAL_DISCORD_WEBHOOK_URL//\'/\'"\'"\'}'
export BIZZAL_DISCORD_BOT_TOKEN='${BIZZAL_DISCORD_BOT_TOKEN//\'/\'"\'"\'}'
export BIZZAL_DISCORD_CHANNEL_ID='${BIZZAL_DISCORD_CHANNEL_ID//\'/\'"\'"\'}'
export BIZZAL_DISCORD_APPROVER_USER_IDS='${BIZZAL_DISCORD_APPROVER_USER_IDS//\'/\'"\'"\'}'
export BIZZAL_PUBLISH_CMD='${BIZZAL_PUBLISH_CMD//\'/\'"\'"\'}'
EOF

if ! grep -q 'source ~/.config/bizzal.env' "$BASHRC_FILE" 2>/dev/null; then
  echo 'source ~/.config/bizzal.env' >> "$BASHRC_FILE"
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

echo
echo "Saved and loaded environment values."
for v in "${required[@]}"; do
  if [[ -n "${!v:-}" ]]; then
    echo "OK  $v"
  else
    echo "MISS $v"
  fi
done

echo
echo "Next steps:"
echo "1) Request approval:  bin/core/discord_publish_gate.py request --day \"\$(date +%F)\""
echo "2) Publish check:     bin/core/discord_publish_gate.py check --publish"
