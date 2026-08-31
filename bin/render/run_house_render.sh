#!/usr/bin/env bash
set -euo pipefail

DAY="${1:-$(date +%F)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# House preset defaults (override any of these via environment if desired).
export BIZZAL_TEXT_STYLE="${BIZZAL_TEXT_STYLE:-bg_safe}"
export BIZZAL_ENABLE_TTS="${BIZZAL_ENABLE_TTS:-1}"
export BIZZAL_ENABLE_BG_MUSIC="${BIZZAL_ENABLE_BG_MUSIC:-1}"
export BIZZAL_ENABLE_BG_IMAGE="${BIZZAL_ENABLE_BG_IMAGE:-1}"
export BIZZAL_BG_IMAGE_MODE="${BIZZAL_BG_IMAGE_MODE:-per_screen}"
export BIZZAL_BG_IMAGE_XFADE_SEC="${BIZZAL_BG_IMAGE_XFADE_SEC:-0.45}"
export BIZZAL_BG_IMAGE_MOTION="${BIZZAL_BG_IMAGE_MOTION:-1}"
export BIZZAL_BG_IMAGE_MOTION_PIXELS="${BIZZAL_BG_IMAGE_MOTION_PIXELS:-24}"
export BIZZAL_BG_IMAGE_MOTION_SPEED="${BIZZAL_BG_IMAGE_MOTION_SPEED:-0.20}"
export BIZZAL_AUDIO_PROFILE="${BIZZAL_AUDIO_PROFILE:-cinematic}"
export BIZZAL_BG_MUSIC_TAIL_SEC="${BIZZAL_BG_MUSIC_TAIL_SEC:-3}"
# No opening black pad or fade-in: the ~2s black + 2s fade meant the video's
# first ~4s were black, so Instagram's feed preview (which uses an early video
# frame, not the cover_url) showed a black tile and scrollers couldn't tell what
# the Reel was. Open hard on the hook art instead -- frame 0 is content. (Any
# fade-in starts from black, so it MUST be 0, not just short, to fix the thumbnail.)
export BIZZAL_INTRO_PAD_SEC="${BIZZAL_INTRO_PAD_SEC:-0}"
export BIZZAL_INTRO_FADE_SEC="${BIZZAL_INTRO_FADE_SEC:-0}"
export BIZZAL_END_FADE_SEC="${BIZZAL_END_FADE_SEC:-4}"
export BIZZAL_END_BLACK_PAD_SEC="${BIZZAL_END_BLACK_PAD_SEC:-2}"

# Keep optional manual tuning available while providing stable house defaults.
export BIZZAL_BG_MUSIC_GAIN="${BIZZAL_BG_MUSIC_GAIN:-0.58}"
export BIZZAL_BG_DUCK_THRESHOLD="${BIZZAL_BG_DUCK_THRESHOLD:-0.12}"
export BIZZAL_BG_DUCK_RATIO="${BIZZAL_BG_DUCK_RATIO:-1.6}"
export BIZZAL_BG_DUCK_ATTACK_MS="${BIZZAL_BG_DUCK_ATTACK_MS:-30}"
export BIZZAL_BG_DUCK_RELEASE_MS="${BIZZAL_BG_DUCK_RELEASE_MS:-700}"
export BIZZAL_BG_TONE_WARMTH_DB="${BIZZAL_BG_TONE_WARMTH_DB:-3.2}"
export BIZZAL_BG_TONE_PRESENCE_DB="${BIZZAL_BG_TONE_PRESENCE_DB:--2.8}"
export BIZZAL_BG_MONO_WIDEN_MS="${BIZZAL_BG_MONO_WIDEN_MS:-16}"
export BIZZAL_FINAL_LOUDNORM="${BIZZAL_FINAL_LOUDNORM:-1}"

echo "[house] day=$DAY text_style=$BIZZAL_TEXT_STYLE tts=$BIZZAL_ENABLE_TTS music=$BIZZAL_ENABLE_BG_MUSIC profile=$BIZZAL_AUDIO_PROFILE" >&2

"$REPO_ROOT/bin/render/render_atom.sh" "$DAY"
