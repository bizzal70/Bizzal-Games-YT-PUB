#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DAY="${BIZZAL_DAY:-$(date +%F)}"
VIDEO_BY_DAY="$REPO_ROOT/data/renders/by_day/${DAY}.mp4"
VIDEO_LATEST="$REPO_ROOT/data/renders/latest/latest.mp4"

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

"$REPO_ROOT/bin/upload/upload_youtube.py" --day "$DAY" --video "$VIDEO_PATH"
