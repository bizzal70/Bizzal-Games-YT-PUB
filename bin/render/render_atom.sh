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

# Dynamic segment pacing (defaults tuned for 30s Shorts).
# Hook + body page 1 share segment 1, body page 2 is segment 2, CTA is segment 3.
DUR="${BIZZAL_SHORTS_DURATION:-30}"
HOOK_MIN=6
HOOK_MAX=12
CTA_MIN=5
CTA_MAX=10
BODY_MIN=8

CATEGORY="$(jq -r '.category // ""' "$ATOM" | tr '[:upper:]' '[:lower:]')"
CTA_PROFILE="default"
case "$CATEGORY" in
  encounter_seed|monster_tactic)
    CTA_MIN=6
    CTA_MAX=11
    CTA_PROFILE="combat_weighted"
    ;;
  rules_ruling|rules_myth)
    CTA_MIN=4
    CTA_MAX=8
    CTA_PROFILE="rules_compact"
    ;;
  spell_use_case|item_spotlight|character_micro_tip)
    CTA_MIN=5
    CTA_MAX=9
    CTA_PROFILE="utility_balanced"
    ;;
esac

count_words() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo 1
    return
  fi
  local n
  n="$(tr -s '[:space:]' ' ' < "$f" | wc -w | tr -d ' ')"
  if [[ -z "$n" || "$n" -lt 1 ]]; then
    echo 1
  else
    echo "$n"
  fi
}

clamp_int() {
  local val="$1" min="$2" max="$3"
  if (( val < min )); then
    echo "$min"
  elif (( val > max )); then
    echo "$max"
  else
    echo "$val"
  fi
}

HOOK_WORDS="$(count_words "$HOOK_TXT")"
BODY_WORDS="$(count_words "$BODY_TXT")"
CTA_WORDS="$(count_words "$CTA_TXT")"
TOTAL_WORDS=$(( HOOK_WORDS + BODY_WORDS + CTA_WORDS ))

HOOK_SEC=$(( DUR * HOOK_WORDS / TOTAL_WORDS ))
CTA_SEC=$(( DUR * CTA_WORDS / TOTAL_WORDS ))

HOOK_SEC="$(clamp_int "$HOOK_SEC" "$HOOK_MIN" "$HOOK_MAX")"
CTA_SEC="$(clamp_int "$CTA_SEC" "$CTA_MIN" "$CTA_MAX")"
BODY_SEC=$(( DUR - HOOK_SEC - CTA_SEC ))

# Ensure body has enough time; borrow from hook/cta while preserving mins.
if (( BODY_SEC < BODY_MIN )); then
  NEED=$(( BODY_MIN - BODY_SEC ))

  HOOK_SPARE=$(( HOOK_SEC - HOOK_MIN ))
  if (( HOOK_SPARE > 0 )); then
    TAKE=$(( NEED < HOOK_SPARE ? NEED : HOOK_SPARE ))
    HOOK_SEC=$(( HOOK_SEC - TAKE ))
    BODY_SEC=$(( BODY_SEC + TAKE ))
    NEED=$(( NEED - TAKE ))
  fi

  CTA_SPARE=$(( CTA_SEC - CTA_MIN ))
  if (( NEED > 0 && CTA_SPARE > 0 )); then
    TAKE=$(( NEED < CTA_SPARE ? NEED : CTA_SPARE ))
    CTA_SEC=$(( CTA_SEC - TAKE ))
    BODY_SEC=$(( BODY_SEC + TAKE ))
  fi
fi

HOOK_END="$HOOK_SEC"
BODY_END=$(( HOOK_SEC + BODY_SEC ))

echo "[render] pacing words hook=$HOOK_WORDS body=$BODY_WORDS cta=$CTA_WORDS total=$TOTAL_WORDS" >&2
echo "[render] pacing secs hook=$HOOK_SEC body=$BODY_SEC cta=$CTA_SEC dur=$DUR" >&2
echo "[render] pacing profile category=$CATEGORY cta_profile=$CTA_PROFILE cta_min=$CTA_MIN cta_max=$CTA_MAX" >&2

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
drawtext=${COMMON}:textfile=${HOOK_FILE}:fontsize=64:${XPOS}:y=120:enable='between(t,0,${HOOK_END})',\
drawtext=${COMMON}:textfile=${BODY1_FILE}:fontsize=46:${XPOS}:y=340:enable='between(t,0,${HOOK_END})',\
drawtext=${COMMON}:textfile=${BODY2_FILE}:fontsize=48:${XPOS}:y=260:enable='between(t,${HOOK_END},${BODY_END})',\
drawtext=${COMMON}:textfile=${CTA_FILE}:fontsize=52:${XPOS}:y=420:enable='between(t,${BODY_END},${DUR})'\
"

ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=black:s=1080x1920:d=${DUR}:r=30" \
  -vf "$VF" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart \
  "$OUT"

cp -f "$OUT" "$LATEST"
echo "[render] wrote $OUT" >&2
echo "[render] updated $LATEST" >&2
