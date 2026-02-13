#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DAY="${BIZZAL_DAY:-$(date +%F)}"

"$REPO_ROOT/bin/upload/upload_youtube.py" --day "$DAY" --video "$REPO_ROOT/data/renders/latest/latest.mp4"
