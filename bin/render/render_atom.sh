#!/usr/bin/env bash
set -euo pipefail

DAY="${1:-$(date +%F)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ATOM="$ROOT/data/atoms/validated/${DAY}.json"
OUT_DIR="$ROOT/data/renders/by_day"
LATEST_DIR="$ROOT/data/renders/latest"

mkdir -p "$OUT_DIR" "$LATEST_DIR"

if [[ ! -f "$ATOM" ]]; then
  echo "[render] missing validated atom: $ATOM" >&2
  exit 1
fi

HOOK="$(jq -r '.script.hook // ""' "$ATOM")"
BODY="$(jq -r '.script.body // ""' "$ATOM")"
CTA="$(jq -r '.script.cta  // ""' "$ATOM")"

# Basic word-count duration: ~140 wpm, min 12s, max 30s
WORDS="$(printf "%s %s %s" "$HOOK" "$BODY" "$CTA" | wc -w | tr -d ' ')"
DUR="$(python3 - <<PY
w=$WORDS
secs=int(max(12, min(30, (w/140)*60)))
print(secs)
PY
)"

OUT="$OUT_DIR/${DAY}.mp4"
LATEST="$LATEST_DIR/latest.mp4"

echo "[render] DAY=$DAY words=$WORDS dur=${DUR}s"
echo "[render] out=$OUT"

# Text layout
# - drawtext uses a font; DejaVuSans is usually present on Ubuntu
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
if [[ ! -f "$FONT" ]]; then
  echo "[render] missing font $FONT" >&2
  exit 1
fi

# Escape for drawtext (basic)
ESC() { printf "%s" "$1" | sed 's/:/\\:/g; s/%/\\%/g; s/\\/\\\\/g; s/'\''/\\'\''/g'; }

HOOK_E="$(ESC "$HOOK")"
BODY_E="$(ESC "$BODY")"
CTA_E="$(ESC "$CTA")"

ffmpeg -y \
  -f lavfi -i "color=c=black:s=1080x1920:d=${DUR}" \
  -vf "\
drawtext=fontfile=${FONT}:text='${HOOK_E}':x=60:y=120:fontsize=64:line_spacing=8:wrap=1, \
drawtext=fontfile=${FONT}:text='${BODY_E}':x=60:y=320:fontsize=44:line_spacing=10:wrap=1, \
drawtext=fontfile=${FONT}:text='${CTA_E}':x=60:y=1660:fontsize=44:line_spacing=10:wrap=1" \
  -r 30 -pix_fmt yuv420p \
  "$OUT"

cp -f "$OUT" "$LATEST"
echo "[render] wrote $OUT"
echo "[render] updated $LATEST"
