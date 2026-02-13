#!/usr/bin/env bash
set -euo pipefail

DAY="${1:-$(date +%F)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ATOM="$REPO_ROOT/data/atoms/validated/${DAY}.json"
OUT="$REPO_ROOT/data/renders/by_day/${DAY}.mp4"
LATEST="$REPO_ROOT/data/renders/latest/latest.mp4"
VOICE_WAV="$REPO_ROOT/data/renders/by_day/${DAY}.voice.wav"
LATEST_VOICE_WAV="$REPO_ROOT/data/renders/latest/latest.voice.wav"
TMPDIR="$REPO_ROOT/data/renders/tmp/${DAY}"
VIDEO_ONLY="$TMPDIR/video_only.mp4"

mkdir -p "$(dirname "$OUT")" "$(dirname "$LATEST")" "$TMPDIR"

TTS_ENABLED="${BIZZAL_ENABLE_TTS:-0}"
TTS_TIMING_MODE="${BIZZAL_TTS_TIMING_MODE:-per_screen}"

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
BODY_WRAP_WIDTH=42
python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$BODY_TXT" --out "$BODY_TXT" --width "$BODY_WRAP_WIDTH"
python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$CTA_TXT"  --out "$CTA_TXT"  --width 40

PAGEDIR="$TMPDIR/pages"
mkdir -p "$PAGEDIR"

# Body can span multiple pages; CTA is its own final page.
# Tune max lines/page and max page count for smoother reading cadence.
BODY_MAXLINES="${BIZZAL_BODY_MAXLINES:-7}"
BODY_MAX_PAGES="${BIZZAL_BODY_MAX_PAGES:-3}"
BODY_PAGES="$(python3 "$REPO_ROOT/bin/render/paginate_lines.py" --infile "$BODY_TXT" --outdir "$PAGEDIR" --prefix body --maxlines "$BODY_MAXLINES")"
if (( BODY_PAGES > BODY_MAX_PAGES )); then
  BODY_LINE_COUNT="$(grep -cve '^[[:space:]]*$' "$BODY_TXT" || true)"
  if [[ -z "$BODY_LINE_COUNT" || "$BODY_LINE_COUNT" -lt 1 ]]; then
    BODY_LINE_COUNT=1
  fi
  ADJ_MAXLINES=$(( (BODY_LINE_COUNT + BODY_MAX_PAGES - 1) / BODY_MAX_PAGES ))
  BODY_PAGES="$(python3 "$REPO_ROOT/bin/render/paginate_lines.py" --infile "$BODY_TXT" --outdir "$PAGEDIR" --prefix body --maxlines "$ADJ_MAXLINES")"
fi
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

probe_duration() {
  local f="$1"
  ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$f" 2>/dev/null || echo 0
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
CTA_FILE="$PAGEDIR/cta.txt"

BODY_PAGE_COUNT="$BODY_PAGES"
BODY_LAST_MIN_WORDS="${BIZZAL_BODY_LAST_MIN_WORDS:-5}"
if (( BODY_PAGE_COUNT > 1 )); then
  LAST_FILE="$PAGEDIR/body${BODY_PAGE_COUNT}.txt"
  PREV_FILE="$PAGEDIR/body$((BODY_PAGE_COUNT - 1)).txt"
  LAST_WORDS="$(count_words "$LAST_FILE")"
  if (( LAST_WORDS < BODY_LAST_MIN_WORDS )); then
    LAST_WORDS_BEFORE="$LAST_WORDS"
    MERGED_BODY="$TMPDIR/body_merged.txt"
    python3 - "$PREV_FILE" "$LAST_FILE" "$MERGED_BODY" <<'PY'
import pathlib, sys
p1 = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
p2 = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
combined = " ".join((p1 + " " + p2).split())
pathlib.Path(sys.argv[3]).write_text(combined + "\n", encoding="utf-8")
PY
    python3 "$REPO_ROOT/bin/render/wrap_text.py" --in "$MERGED_BODY" --out "$PREV_FILE" --width "$BODY_WRAP_WIDTH"
    : > "$LAST_FILE"
    BODY_PAGE_COUNT=$(( BODY_PAGE_COUNT - 1 ))
    echo "[render] anti-orphan merged tiny final body page words_before=$LAST_WORDS_BEFORE min_words=$BODY_LAST_MIN_WORDS" >&2
  fi
fi

BODY_WORDS_LIST=()
BODY_LINES_MAX=0
for ((i=1; i<=BODY_PAGE_COUNT; i++)); do
  PAGE_FILE="$PAGEDIR/body${i}.txt"
  WORDS_I="$(count_words "$PAGE_FILE")"
  LINES_I="$(count_nonempty_lines "$PAGE_FILE")"
  BODY_WORDS_LIST+=("$WORDS_I")
  if (( LINES_I > BODY_LINES_MAX )); then
    BODY_LINES_MAX="$LINES_I"
  fi
done

BODY_FONT_SIZE=44
if (( BODY_LINES_MAX >= 10 )); then
  BODY_FONT_SIZE=42
fi
if (( BODY_LINES_MAX >= 12 )); then
  BODY_FONT_SIZE=40
fi

BODY_PAGE_MIN_SEC="${BIZZAL_BODY_PAGE_MIN_SEC:-4}"
BODY_SECS_LINE="$(python3 - <<'PY' "$BODY_SEC" "$BODY_PAGE_MIN_SEC" "${BODY_WORDS_LIST[*]}"
import sys
body_sec = int(sys.argv[1])
min_sec = int(sys.argv[2])
words = [int(x) for x in sys.argv[3].split() if x.strip()]
if not words:
    print(body_sec)
    raise SystemExit(0)
if len(words) == 1:
    print(body_sec)
    raise SystemExit(0)
total = sum(words) or len(words)
secs = [max(min_sec, int(round(body_sec * (w / total)))) for w in words]
delta = body_sec - sum(secs)
if delta > 0:
    i = 0
    while delta > 0:
        secs[i % len(secs)] += 1
        i += 1
        delta -= 1
elif delta < 0:
    i = 0
    while delta < 0:
        idx = i % len(secs)
        if secs[idx] > min_sec:
            secs[idx] -= 1
            delta += 1
        i += 1
        if i > 10000:
            break
print(" ".join(str(x) for x in secs))
PY
)"
read -r -a BODY_SECS <<< "$BODY_SECS_LINE"

BODY_END="$HOOK_END"
BODY_ENDS=()
for ((i=0; i<${#BODY_SECS[@]}; i++)); do
  BODY_END=$(( BODY_END + BODY_SECS[i] ))
  BODY_ENDS+=("$BODY_END")
done

PREBUILT_TTS=0
if [[ "$TTS_ENABLED" == "1" && "$TTS_TIMING_MODE" == "per_screen" && -x "$REPO_ROOT/bin/render/synthesize_tts.py" ]]; then
  TTS_SEGDIR="$TMPDIR/tts_segments"
  mkdir -p "$TTS_SEGDIR"

  SEG_FAIL=0
  TTS_SEG_FILES=()

  HOOK_SEG_WAV="$TTS_SEGDIR/01_hook.wav"
  if "$REPO_ROOT/bin/render/synthesize_tts.py" --text-file "$HOOK_FILE" --out "$HOOK_SEG_WAV"; then
    TTS_SEG_FILES+=("$HOOK_SEG_WAV")
  else
    SEG_FAIL=1
  fi

  for ((i=1; i<=BODY_PAGE_COUNT; i++)); do
    PAGE_FILE="$PAGEDIR/body${i}.txt"
    PAGE_SEG_WAV="$TTS_SEGDIR/$(printf '%02d' $((i+1)))_body${i}.wav"
    if "$REPO_ROOT/bin/render/synthesize_tts.py" --text-file "$PAGE_FILE" --out "$PAGE_SEG_WAV"; then
      TTS_SEG_FILES+=("$PAGE_SEG_WAV")
    else
      SEG_FAIL=1
      break
    fi
  done

  CTA_SEG_WAV="$TTS_SEGDIR/99_cta.wav"
  if (( SEG_FAIL == 0 )); then
    if "$REPO_ROOT/bin/render/synthesize_tts.py" --text-file "$CTA_FILE" --out "$CTA_SEG_WAV"; then
      TTS_SEG_FILES+=("$CTA_SEG_WAV")
    else
      SEG_FAIL=1
    fi
  fi

  if (( SEG_FAIL == 0 )); then
    SEG_DURS=()
    for wav in "${TTS_SEG_FILES[@]}"; do
      SEG_DURS+=("$(probe_duration "$wav")")
    done

    TTS_BODY_PAGE_MIN_SEC="${BIZZAL_TTS_BODY_PAGE_MIN_SEC:-5}"
    TTS_SEGMENT_PAD_SEC="${BIZZAL_TTS_SEGMENT_PAD_SEC:-0.20}"

    TIMING_LINES="$(python3 - <<'PY' "$DUR" "${SEG_DURS[*]}" "$TTS_BODY_PAGE_MIN_SEC" "$TTS_SEGMENT_PAD_SEC"
import math, sys
base_target = int(float(sys.argv[1]))
durs = [float(x) for x in sys.argv[2].split() if x.strip()]
body_min = max(1, int(float(sys.argv[3])))
pad_sec = max(0.0, float(sys.argv[4]))

if not durs:
    print(base_target)
    print("")
    raise SystemExit(0)

mins = [1 for _ in durs]
for i in range(1, max(1, len(durs) - 1)):
    mins[i] = body_min

secs = []
for i, dur in enumerate(durs):
    hold = int(math.ceil(max(0.0, dur) + pad_sec))
    secs.append(max(mins[i], hold))

target = max(base_target, sum(secs), int(math.ceil(sum(durs))))
print(target)
print(" ".join(str(x) for x in secs))
PY
    )"

    DUR_FROM_TTS="$(echo "$TIMING_LINES" | sed -n '1p')"
    SECS_FROM_TTS="$(echo "$TIMING_LINES" | sed -n '2p')"
    if [[ -n "$DUR_FROM_TTS" && -n "$SECS_FROM_TTS" ]]; then
      read -r -a SCREEN_SECS <<< "$SECS_FROM_TTS"
      if (( ${#SCREEN_SECS[@]} == BODY_PAGE_COUNT + 2 )); then
        DUR="$DUR_FROM_TTS"
        HOOK_SEC="${SCREEN_SECS[0]}"
        CTA_SEC="${SCREEN_SECS[$(( ${#SCREEN_SECS[@]} - 1 ))]}"
        BODY_SECS=()
        for ((i=0; i<BODY_PAGE_COUNT; i++)); do
          BODY_SECS+=("${SCREEN_SECS[$((i+1))]}")
        done

        HOOK_END="$HOOK_SEC"
        BODY_END="$HOOK_END"
        BODY_ENDS=()
        for ((i=0; i<${#BODY_SECS[@]}; i++)); do
          BODY_END=$(( BODY_END + BODY_SECS[i] ))
          BODY_ENDS+=("$BODY_END")
        done
      fi
    fi

    CONCAT_LIST="$TTS_SEGDIR/segments.txt"
    : > "$CONCAT_LIST"
    for wav in "${TTS_SEG_FILES[@]}"; do
      echo "file $wav" >> "$CONCAT_LIST"
    done
    if ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "$CONCAT_LIST" -c:a pcm_s16le "$VOICE_WAV"; then
      PREBUILT_TTS=1
      echo "[render] tts timing mode=per_screen body_min_sec=$TTS_BODY_PAGE_MIN_SEC seg_pad_sec=$TTS_SEGMENT_PAD_SEC durations=${SEG_DURS[*]} screen_secs=${SCREEN_SECS[*]} dur=$DUR" >&2
    fi
  else
    echo "[render] per-screen tts timing failed; using word-based screen timing" >&2
  fi
fi

echo "[render] body pages count=$BODY_PAGE_COUNT words=${BODY_WORDS_LIST[*]}" >&2
echo "[render] body pages secs ${BODY_SECS[*]}" >&2
echo "[render] body layout lines_max=$BODY_LINES_MAX body_font_size=$BODY_FONT_SIZE last_min_words=$BODY_LAST_MIN_WORDS" >&2
echo "[render] text style name=$TEXT_STYLE box_alpha=$BOX_ALPHA box_borderw=$BOX_BORDER_W borderw=$BORDER_W" >&2

VF="drawtext=${COMMON}:textfile=${HOOK_FILE}:fontsize=66:${XPOS}:y=(h-text_h)/2:enable='between(t,0,${HOOK_END})',"
PAGE_START="$HOOK_END"
for ((i=1; i<=BODY_PAGE_COUNT; i++)); do
  PAGE_END="${BODY_ENDS[$((i-1))]}"
  PAGE_FILE="$PAGEDIR/body${i}.txt"
  VF+="drawtext=${COMMON}:textfile=${PAGE_FILE}:fontsize=${BODY_FONT_SIZE}:${XPOS}:y=(h-text_h)/2:enable='between(t,${PAGE_START},${PAGE_END})',"
  PAGE_START="$PAGE_END"
done
VF+="drawtext=${COMMON}:textfile=${CTA_FILE}:fontsize=50:${XPOS}:y=(h-text_h)/2:enable='between(t,${BODY_END},${DUR})'"

ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=black:s=1080x1920:d=${DUR}:r=30" \
  -vf "$VF" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart \
  "$VIDEO_ONLY"

TTS_OK=0
if [[ "$TTS_ENABLED" == "1" ]]; then
  if (( PREBUILT_TTS == 1 )) && [[ -f "$VOICE_WAV" ]]; then
    TTS_OK=1
  elif [[ -x "$REPO_ROOT/bin/render/synthesize_tts.py" ]]; then
    if "$REPO_ROOT/bin/render/synthesize_tts.py" --atom "$ATOM" --out "$VOICE_WAV"; then
      TTS_OK=1
    else
      echo "[render] tts synth failed; continuing with text-only video" >&2
    fi
  else
    echo "[render] tts synth script missing; continuing with text-only video" >&2
  fi
fi

if (( TTS_OK == 1 )); then
  VIDEO_PADDED="$TMPDIR/video_padded.mp4"
  MUX_VIDEO="$VIDEO_ONLY"

  VIDEO_SEC="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$VIDEO_ONLY" 2>/dev/null || echo 0)"
  AUDIO_SEC="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$VOICE_WAV" 2>/dev/null || echo 0)"
  PAD_SEC="$(python3 - <<'PY' "$VIDEO_SEC" "$AUDIO_SEC"
import sys
try:
    v = float(sys.argv[1])
except Exception:
    v = 0.0
try:
    a = float(sys.argv[2])
except Exception:
    a = 0.0
pad = (a + 0.15) - v
print(f"{pad:.3f}" if pad > 0 else "0")
PY
  )"

  if [[ "$PAD_SEC" != "0" ]]; then
    ffmpeg -y -hide_banner -loglevel error \
      -i "$VIDEO_ONLY" \
      -vf "tpad=stop_mode=clone:stop_duration=${PAD_SEC}" \
      -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart \
      "$VIDEO_PADDED"
    MUX_VIDEO="$VIDEO_PADDED"
    echo "[render] video padded by ${PAD_SEC}s to match tts audio (${AUDIO_SEC}s)" >&2
  fi

  ffmpeg -y -hide_banner -loglevel error \
    -i "$MUX_VIDEO" \
    -i "$VOICE_WAV" \
    -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart \
    "$OUT"
  cp -f "$VOICE_WAV" "$LATEST_VOICE_WAV"
  echo "[render] wrote $VOICE_WAV" >&2
else
  cp -f "$VIDEO_ONLY" "$OUT"
fi

cp -f "$OUT" "$LATEST"
echo "[render] wrote $OUT" >&2
echo "[render] updated $LATEST" >&2
