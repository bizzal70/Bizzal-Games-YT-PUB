#!/usr/bin/env bash
set -euo pipefail

DAY="${1:-$(date +%F)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ATOM="$REPO_ROOT/data/atoms/validated/${DAY}.json"
OUT="$REPO_ROOT/data/renders/by_day/${DAY}.mp4"
LATEST="$REPO_ROOT/data/renders/latest/latest.mp4"
TMPDIR="$REPO_ROOT/data/renders/tmp/${DAY}"

mkdir -p "$(dirname "$OUT")" "$(dirname "$LATEST")" "$TMPDIR"

cleanup() {
  if [[ "${DEBUG_RENDER:-0}" == "1" ]]; then
    echo "[render] DEBUG_RENDER=1 keeping tmpdir=$TMPDIR" >&2
  else
    rm -rf "$TMPDIR"
  fi
}
trap cleanup EXIT

if [[ ! -f "$ATOM" ]]; then
  echo "[render] missing validated atom: $ATOM" >&2
  exit 1
fi

HOOK_TXT="$TMPDIR/hook.txt"
BODY_TXT="$TMPDIR/body.txt"
CTA_TXT="$TMPDIR/cta.txt"

jq -r '.script.hook // ""' "$ATOM" > "$HOOK_TXT"
jq -r '.script.body // ""' "$ATOM" > "$BODY_TXT"
jq -r '.script.cta  // ""' "$ATOM" > "$CTA_TXT"

# Wrap first, then paginate by line-count so nothing can overflow the frame.
python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$HOOK_TXT" --out "$HOOK_TXT" --width 30
python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$BODY_TXT" --out "$BODY_TXT" --width 46
python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$CTA_TXT"  --out "$CTA_TXT"  --width 46

PAGEDIR="$TMPDIR/pages"
mkdir -p "$PAGEDIR"

# Body becomes up to 2 pages; CTA is its own final page.
# Tune maxlines down if you want bigger text.
BODY_PAGES="$(python3 "$REPO_ROOT/bin/render/paginate_lines.py" --infile "$BODY_TXT" --outdir "$PAGEDIR" --prefix body --maxlines 9)"
cp -f "$HOOK_TXT" "$PAGEDIR/hook.txt"
cp -f "$CTA_TXT"  "$PAGEDIR/cta.txt"

# We'll do: 0-10 hook+body1, 10-20 body2 (if present), 20-30 cta
DUR=30

FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
COMMON="fontfile=${FONT}:fontcolor=white:line_spacing=12:fix_bounds=1:box=1:boxcolor=black@0.72:boxborderw=22:borderw=2:bordercolor=black@0.95:shadowcolor=black@0.9:shadowx=2:shadowy=2"
XPOS="x=(w-text_w)/2"

HOOK_FILE="$PAGEDIR/hook.txt"
BODY1_FILE="$PAGEDIR/body1.txt"
BODY2_FILE="$PAGEDIR/body2.txt"
CTA_FILE="$PAGEDIR/cta.txt"

# If body2 doesn't exist, just reuse body1 (so screen 2 isn't blank).
if [[ ! -f "$BODY2_FILE" ]]; then
  cp -f "$BODY1_FILE" "$BODY2_FILE"
fi

VF="\
drawtext=${COMMON}:textfile=${HOOK_FILE}:fontsize=64:${XPOS}:y=120:enable='between(t,0,10)',\
drawtext=${COMMON}:textfile=${BODY1_FILE}:fontsize=46:${XPOS}:y=340:enable='between(t,0,10)',\
drawtext=${COMMON}:textfile=${BODY2_FILE}:fontsize=48:${XPOS}:y=260:enable='between(t,10,20)',\
drawtext=${COMMON}:textfile=${CTA_FILE}:fontsize=52:${XPOS}:y=420:enable='between(t,20,30)'\
"

ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=black:s=1080x1920:d=${DUR}:r=30" \
  -vf "$VF" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart \
  "$OUT"

cp -f "$OUT" "$LATEST"
echo "[render] wrote $OUT" >&2
echo "[render] updated $LATEST" >&2
