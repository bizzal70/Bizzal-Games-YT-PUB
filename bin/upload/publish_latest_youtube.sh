#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DAY="${BIZZAL_DAY:-$(date +%F)}"
VIDEO_BY_DAY="$REPO_ROOT/data/renders/by_day/${DAY}.mp4"
VIDEO_LATEST="$REPO_ROOT/data/renders/latest/latest.mp4"
VOICE_BY_DAY="$REPO_ROOT/data/renders/by_day/${DAY}.voice.wav"
MUSIC_BY_DAY="$REPO_ROOT/data/renders/by_day/${DAY}.music.wav"
BG_BY_DAY="$REPO_ROOT/data/renders/by_day/${DAY}.bg.png"

if [[ -f "$VIDEO_BY_DAY" ]]; then
	VIDEO_PATH="$VIDEO_BY_DAY"
elif [[ "${BIZZAL_ALLOW_LATEST_FALLBACK:-0}" == "1" && -f "$VIDEO_LATEST" ]]; then
	echo "[publish_latest_youtube] WARN: day-specific render missing for ${DAY}; falling back to latest.mp4" >&2
	VIDEO_PATH="$VIDEO_LATEST"
else
	echo "[publish_latest_youtube] ERROR: missing day-specific render: $VIDEO_BY_DAY" >&2
	echo "[publish_latest_youtube] Render this day first, or set BIZZAL_ALLOW_LATEST_FALLBACK=1 to permit fallback." >&2
	exit 3
fi

REQUIRE_ENRICHED_RENDER="${BIZZAL_REQUIRE_ENRICHED_RENDER:-1}"
EXPECT_TTS="${BIZZAL_EXPECT_TTS:-1}"
EXPECT_MUSIC="${BIZZAL_EXPECT_MUSIC:-1}"
EXPECT_BG_IMAGE="${BIZZAL_EXPECT_BG_IMAGE:-1}"

if [[ "$REQUIRE_ENRICHED_RENDER" == "1" ]]; then
	missing=()
	if [[ "$EXPECT_TTS" == "1" && ! -f "$VOICE_BY_DAY" ]]; then
		missing+=("$VOICE_BY_DAY")
	fi
	if [[ "$EXPECT_MUSIC" == "1" && ! -f "$MUSIC_BY_DAY" ]]; then
		missing+=("$MUSIC_BY_DAY")
	fi
	if [[ "$EXPECT_BG_IMAGE" == "1" && ! -f "$BG_BY_DAY" ]]; then
		missing+=("$BG_BY_DAY")
	fi

	if (( ${#missing[@]} > 0 )); then
		echo "[publish_latest_youtube] ERROR: enriched render artifacts missing; refusing upload." >&2
		for path in "${missing[@]}"; do
			echo "  - missing: $path" >&2
		done
		echo "[publish_latest_youtube] Render with media enabled before publishing, or set BIZZAL_REQUIRE_ENRICHED_RENDER=0 for intentional plain uploads." >&2
		exit 9
	fi
fi

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
	"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/bin/upload/upload_youtube.py" --day "$DAY" --video "$VIDEO_PATH"
else
	"$REPO_ROOT/bin/upload/upload_youtube.py" --day "$DAY" --video "$VIDEO_PATH"
fi
