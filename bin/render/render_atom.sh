#!/usr/bin/env bash
set -euo pipefail

command -v jq >/dev/null || { echo "[render] missing dependency: jq" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "[render] missing dependency: ffmpeg" >&2; exit 1; }

DAY="${1:-$(date +%F)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ATOM="$ROOT/data/atoms/validated/${DAY}.json"
OUT_DIR="$ROOT/data/renders/by_day"
LATEST_DIR="$ROOT/data/renders/latest"
TMP_DIR="$ROOT/tmp/render"

mkdir -p "$OUT_DIR" "$LATEST_DIR" "$TMP_DIR"

if [[ ! -f "$ATOM" ]]; then
  echo "[render] missing validated atom: $ATOM" >&2
  exit 1
fi

HOOK="$(jq -r '.script.hook // ""' "$ATOM")"
BODY="$(jq -r '.script.body // ""' "$ATOM")"
CTA="$(jq -r '.script.cta  // ""' "$ATOM")"

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

FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
if [[ ! -f "$FONT" ]]; then
  echo "[render] missing font $FONT" >&2
  exit 1
fi

# Write text to files to avoid drawtext escaping issues
HOOK_TXT="$TMP_DIR/hook.txt"
BODY_TXT="$TMP_DIR/body.txt"
CTA_TXT="$TMP_DIR/cta.txt"

printf "%s\n" "$HOOK" > "$HOOK_TXT"
printf "%s\n" "$BODY" > "$BODY_TXT"
printf "%s\n" "$CTA"  > "$CTA_TXT"

ffmpeg -y \
  -f lavfi -i "color=c=black:s=1080x1920:d=${DUR}:r=30" \
  -vf "\
drawtext=fontfile=${FONT}:textfile=${HOOK_TXT}:reload=1:x=60:y=120:fontsize=64:line_spacing=8:box=1:boxborderw=18:boxcolor=black@0.35, \
drawtext=fontfile=${FONT}:textfile=${BODY_TXT}:reload=1:x=60:y=320:fontsize=44:line_spacing=10:box=1:boxborderw=18:boxcolor=black@0.35, \
drawtext=fontfile=${FONT}:textfile=${CTA_TXT}:reload=1:x=60:y=1660:fontsize=44:line_spacing=10:box=1:boxborderw=18:boxcolor=black@0.35" \
  -pix_fmt yuv420p \
  "$OUT"

cp -f "$OUT" "$LATEST"
echo "[render] wrote $OUT"
echo "[render] updated $LATEST"
