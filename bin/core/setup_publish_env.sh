#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HOME}/.config/bizzal.env"
BASHRC_FILE="${HOME}/.bashrc"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEFAULT_PUBLISH_CMD="$REPO_ROOT/bin/upload/publish_latest_youtube.sh"
MANAGED_BEGIN="# >>> BIZZAL MANAGED ENV >>>"
MANAGED_END="# <<< BIZZAL MANAGED ENV <<<"

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

prompt_value OPENAI_API_KEY "OpenAI API key" 1
prompt_value REPLICATE_API_TOKEN "Replicate API token" 1

if [[ -z "${BIZZAL_YT_CLIENT_SECRETS:-}" ]]; then
  BIZZAL_YT_CLIENT_SECRETS="$HOME/.config/bizzal/youtube_client_secrets.json"
fi
if [[ -z "${BIZZAL_YT_TOKEN_FILE:-}" ]]; then
  BIZZAL_YT_TOKEN_FILE="$HOME/.config/bizzal/youtube_token.json"
fi
if [[ -z "${BIZZAL_YT_OAUTH_MODE:-}" ]]; then
  BIZZAL_YT_OAUTH_MODE="console"
fi
if [[ -z "${BIZZAL_ENABLE_AI:-}" ]]; then
  BIZZAL_ENABLE_AI="1"
fi
if [[ -z "${BIZZAL_ENABLE_AI_SCRIPT:-}" ]]; then
  BIZZAL_ENABLE_AI_SCRIPT="1"
fi

prompt_value BIZZAL_YT_CLIENT_SECRETS "YouTube client secrets path"
prompt_value BIZZAL_YT_TOKEN_FILE "YouTube token file path"
prompt_value BIZZAL_YT_OAUTH_MODE "YouTube OAuth mode (console/local)"

if [[ -z "${BIZZAL_PUBLISH_CMD:-}" && -x "$DEFAULT_PUBLISH_CMD" ]]; then
  BIZZAL_PUBLISH_CMD="$DEFAULT_PUBLISH_CMD"
fi
prompt_value BIZZAL_PUBLISH_CMD "Publish command (exact upload command)"

required=(
  OPENAI_API_KEY
  REPLICATE_API_TOKEN
  BIZZAL_DISCORD_WEBHOOK_URL
  BIZZAL_DISCORD_BOT_TOKEN
  BIZZAL_DISCORD_CHANNEL_ID
  BIZZAL_DISCORD_APPROVER_USER_IDS
  BIZZAL_YT_CLIENT_SECRETS
  BIZZAL_YT_TOKEN_FILE
  BIZZAL_YT_OAUTH_MODE
  BIZZAL_PUBLISH_CMD
)

for v in "${required[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: $v is empty. Re-run setup and provide all values." >&2
    exit 2
  fi
done

if [[ ! -f "${BIZZAL_YT_CLIENT_SECRETS}" ]]; then
  echo "WARN: YouTube client secrets file not found at: ${BIZZAL_YT_CLIENT_SECRETS}" >&2
fi

escape_sq() {
  local s="$1"
  printf "%s" "${s//\'/\'\"\'\"\'}"
}

if [[ -f "$ENV_FILE" ]]; then
  cp -f "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
fi

tmp_file="$ENV_FILE.tmp"

if [[ -f "$ENV_FILE" ]]; then
  awk -v b="$MANAGED_BEGIN" -v e="$MANAGED_END" '
    BEGIN { skip=0 }
    $0==b { skip=1; next }
    $0==e { skip=0; next }
    !skip { print }
  ' "$ENV_FILE" > "$tmp_file"
else
  : > "$tmp_file"
fi

cat >> "$tmp_file" <<EOF
$MANAGED_BEGIN
export OPENAI_API_KEY='$(escape_sq "${OPENAI_API_KEY}")'
export REPLICATE_API_TOKEN='$(escape_sq "${REPLICATE_API_TOKEN}")'
export BIZZAL_DISCORD_WEBHOOK_URL='$(escape_sq "${BIZZAL_DISCORD_WEBHOOK_URL}")'
export BIZZAL_DISCORD_BOT_TOKEN='$(escape_sq "${BIZZAL_DISCORD_BOT_TOKEN}")'
export BIZZAL_DISCORD_CHANNEL_ID='$(escape_sq "${BIZZAL_DISCORD_CHANNEL_ID}")'
export BIZZAL_DISCORD_APPROVER_USER_IDS='$(escape_sq "${BIZZAL_DISCORD_APPROVER_USER_IDS}")'
export BIZZAL_YT_CLIENT_SECRETS='$(escape_sq "${BIZZAL_YT_CLIENT_SECRETS}")'
export BIZZAL_YT_TOKEN_FILE='$(escape_sq "${BIZZAL_YT_TOKEN_FILE}")'
export BIZZAL_YT_OAUTH_MODE='$(escape_sq "${BIZZAL_YT_OAUTH_MODE}")'
export BIZZAL_ENABLE_AI='$(escape_sq "${BIZZAL_ENABLE_AI}")'
export BIZZAL_ENABLE_AI_SCRIPT='$(escape_sq "${BIZZAL_ENABLE_AI_SCRIPT}")'
export BIZZAL_PUBLISH_CMD='$(escape_sq "${BIZZAL_PUBLISH_CMD}")'
$MANAGED_END
EOF

mv "$tmp_file" "$ENV_FILE"
chmod 600 "$ENV_FILE"

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

echo "OK  BIZZAL_ENABLE_AI=${BIZZAL_ENABLE_AI}"
echo "OK  BIZZAL_ENABLE_AI_SCRIPT=${BIZZAL_ENABLE_AI_SCRIPT}"

echo
echo "Next steps:"
echo "1) Request approval:  bin/core/discord_publish_gate.py request --day \"\$(date +%F)\""
echo "2) Publish check:     bin/core/discord_publish_gate.py check --publish"
