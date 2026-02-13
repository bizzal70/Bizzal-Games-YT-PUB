#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="docs/ops_backups"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)
      OUT_DIR="${2:-$OUT_DIR}"
      shift 2
      ;;
    *)
      echo "usage: bin/core/backup_ops_config.sh [--out-dir PATH]" >&2
      exit 2
      ;;
  esac
done

if [[ "$OUT_DIR" != /* ]]; then
  OUT_DIR="$REPO_ROOT/$OUT_DIR"
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET_DIR="$OUT_DIR/$STAMP"
mkdir -p "$TARGET_DIR"

redact_env_file() {
  local src="$1"
  local dest="$2"
  awk -F= '
    BEGIN { OFS="=" }
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { print $0; next }
    {
      key=$1
      sub(/^[[:space:]]+/, "", key)
      sub(/[[:space:]]+$/, "", key)
      if (key ~ /(PASS|PASSWORD|TOKEN|WEBHOOK|SECRET|KEY)/) {
        print key, "REDACTED"
      } else {
        print $0
      }
    }
  ' "$src" > "$dest"
}

# 1) Cron snapshot
if command -v crontab >/dev/null 2>&1; then
  crontab -l > "$TARGET_DIR/crontab.txt" 2>/dev/null || true
else
  echo "# crontab command not available" > "$TARGET_DIR/crontab.txt"
fi

# 2) Runtime env snapshots (redacted)
if [[ -f "$REPO_ROOT/.env.discord_health" ]]; then
  redact_env_file "$REPO_ROOT/.env.discord_health" "$TARGET_DIR/env.discord_health.redacted"
fi
if [[ -f "$REPO_ROOT/.env.health_mail" ]]; then
  redact_env_file "$REPO_ROOT/.env.health_mail" "$TARGET_DIR/env.health_mail.redacted"
fi

# 3) Minimal restore notes + provenance
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
{
  echo "backup_utc=$STAMP"
  echo "repo_root=$REPO_ROOT"
  echo "git_sha=$GIT_SHA"
  echo "files:"
  ls -1 "$TARGET_DIR" | sed 's/^/- /'
  echo
  echo "restore_notes:"
  echo "- review redacted env files and refill real secret values"
  echo "- install cron via: crontab $TARGET_DIR/crontab.txt"
} > "$TARGET_DIR/README.txt"

echo "$TARGET_DIR"
