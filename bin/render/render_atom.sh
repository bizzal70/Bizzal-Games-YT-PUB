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
python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$BODY_TXT" --out "$BODY_TXT" --width 42
python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$CTA_TXT"  --out "$CTA_TXT"  --width 40

PAGEDIR="$TMPDIR/pages"
mkdir -p "$PAGEDIR"

# Body becomes up to 2 pages; CTA is its own final page.
# Tune maxlines down if you want bigger text.
BODY_PAGES="$(python3 "$REPO_ROOT/bin/render/paginate_lines.py" --infile "$BODY_TXT" --outdir "$PAGEDIR" --prefix body --maxlines 9)"
cp -f "$HOOK_TXT" "$PAGEDIR/hook.txt"
cp -f "$CTA_TXT"  "$PAGEDIR/cta.txt"

# Dynamic segment pacing (defaults tuned for 30s Shorts).
# Hook/title is segment 1, body pages are segment 2/3, CTA is the final segment.
DUR="${BIZZAL_SHORTS_DURATION:-30}"
HOOK_MIN=4
HOOK_MAX=8
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

count_nonempty_lines() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo 0
    return
  fi
  grep -cve '^[[:space:]]*$' "$f" || true
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

echo "[render] pacing words hook=$HOOK_WORDS body=$BODY_WORDS cta=$CTA_WORDS total=$TOTAL_WORDS" >&2
echo "[render] pacing secs hook=$HOOK_SEC body=$BODY_SEC cta=$CTA_SEC dur=$DUR" >&2
echo "[render] pacing profile category=$CATEGORY cta_profile=$CTA_PROFILE cta_min=$CTA_MIN cta_max=$CTA_MAX" >&2

FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
TEXT_STYLE="${BIZZAL_TEXT_STYLE:-default}"
BOX_ALPHA="0.72"
BOX_BORDER_W="22"
BORDER_W="2"
BORDER_ALPHA="0.95"
SHADOW_ALPHA="0.9"
SHADOW_X="2"
SHADOW_Y="2"

case "$TEXT_STYLE" in
  bg_safe|bg-safe|background_safe|background-safe)
    BOX_ALPHA="0.84"
    BOX_BORDER_W="28"
    BORDER_W="3"
    BORDER_ALPHA="0.98"
    SHADOW_ALPHA="0.98"
    SHADOW_X="3"
    SHADOW_Y="3"
    ;;
esac

COMMON="fontfile=${FONT}:fontcolor=white:line_spacing=12:text_align=center:fix_bounds=1:box=1:boxcolor=black@${BOX_ALPHA}:boxborderw=${BOX_BORDER_W}:borderw=${BORDER_W}:bordercolor=black@${BORDER_ALPHA}:shadowcolor=black@${SHADOW_ALPHA}:shadowx=${SHADOW_X}:shadowy=${SHADOW_Y}"
XPOS="x=(w-text_w)/2"

HOOK_FILE="$PAGEDIR/hook.txt"
BODY1_FILE="$PAGEDIR/body1.txt"
BODY2_FILE="$PAGEDIR/body2.txt"
CTA_FILE="$PAGEDIR/cta.txt"

BODY2_EXISTS=0
if [[ -f "$BODY2_FILE" ]] && [[ -s "$BODY2_FILE" ]]; then
  BODY2_EXISTS=1
fi

BODY1_WORDS="$(count_words "$BODY1_FILE")"
BODY2_WORDS="$(count_words "$BODY2_FILE")"
BODY2_MIN_WORDS="${BIZZAL_BODY2_MIN_WORDS:-5}"

if (( BODY2_EXISTS == 1 && BODY2_WORDS < BODY2_MIN_WORDS )); then
  BODY2_WORDS_BEFORE="$BODY2_WORDS"
  MERGED_BODY="$TMPDIR/body_merged.txt"
  {
    cat "$BODY1_FILE"
    echo
    cat "$BODY2_FILE"
  } > "$MERGED_BODY"
  mv -f "$MERGED_BODY" "$BODY1_FILE"
  : > "$BODY2_FILE"
  BODY2_EXISTS=0
  BODY1_WORDS="$(count_words "$BODY1_FILE")"
  BODY2_WORDS=0
  echo "[render] anti-orphan merged tiny body2 into body1 body2_words_before=$BODY2_WORDS_BEFORE min_words=$BODY2_MIN_WORDS" >&2
fi

BODY1_LINES="$(count_nonempty_lines "$BODY1_FILE")"
BODY_FONT_SIZE=44
if (( BODY1_LINES >= 10 )); then
  BODY_FONT_SIZE=42
fi

if (( BODY2_EXISTS == 1 )); then
  BODY1_MIN=5
  BODY2_MIN=5
  BODY_PAGES_WORDS=$(( BODY1_WORDS + BODY2_WORDS ))
  BODY1_SEC=$(( BODY_SEC * BODY1_WORDS / BODY_PAGES_WORDS ))
  BODY2_SEC=$(( BODY_SEC - BODY1_SEC ))

  if (( BODY1_SEC < BODY1_MIN )); then
    BODY1_SEC="$BODY1_MIN"
    BODY2_SEC=$(( BODY_SEC - BODY1_SEC ))
  fi
  if (( BODY2_SEC < BODY2_MIN )); then
    BODY2_SEC="$BODY2_MIN"
    BODY1_SEC=$(( BODY_SEC - BODY2_SEC ))
  fi

  if (( BODY1_SEC < BODY1_MIN )); then
    BODY1_SEC="$BODY1_MIN"
    BODY2_SEC=$(( BODY_SEC - BODY1_SEC ))
  fi
else
  BODY1_SEC="$BODY_SEC"
  BODY2_SEC=0
fi

BODY1_END=$(( HOOK_END + BODY1_SEC ))
BODY_END=$(( BODY1_END + BODY2_SEC ))

echo "[render] body pages exists2=$BODY2_EXISTS body1_words=$BODY1_WORDS body2_words=$BODY2_WORDS" >&2
echo "[render] body pages secs body1=$BODY1_SEC body2=$BODY2_SEC" >&2
echo "[render] body layout lines_body1=$BODY1_LINES body_font_size=$BODY_FONT_SIZE body2_min_words=$BODY2_MIN_WORDS" >&2
echo "[render] text style name=$TEXT_STYLE box_alpha=$BOX_ALPHA box_borderw=$BOX_BORDER_W borderw=$BORDER_W" >&2

VF="drawtext=${COMMON}:textfile=${HOOK_FILE}:fontsize=66:${XPOS}:y=(h-text_h)/2:enable='between(t,0,${HOOK_END})',"
VF+="drawtext=${COMMON}:textfile=${BODY1_FILE}:fontsize=${BODY_FONT_SIZE}:${XPOS}:y=(h-text_h)/2:enable='between(t,${HOOK_END},${BODY1_END})',"
if (( BODY2_EXISTS == 1 )); then
  VF+="drawtext=${COMMON}:textfile=${BODY2_FILE}:fontsize=${BODY_FONT_SIZE}:${XPOS}:y=(h-text_h)/2:enable='between(t,${BODY1_END},${BODY_END})',"
fi
VF+="drawtext=${COMMON}:textfile=${CTA_FILE}:fontsize=50:${XPOS}:y=(h-text_h)/2:enable='between(t,${BODY_END},${DUR})'"

ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=black:s=1080x1920:d=${DUR}:r=30" \
  -vf "$VF" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart \
  "$OUT"

cp -f "$OUT" "$LATEST"
echo "[render] wrote $OUT" >&2
echo "[render] updated $LATEST" >&2
