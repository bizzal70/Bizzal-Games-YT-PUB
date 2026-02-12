# Bizzal-Games-YT-PUB

Umbrel-hosted automated “content press” for Bizzal Games.

## What it does
- Generate daily RPG content atoms (JSON)
- Render vertical video (Shorts)
- Optional AI background, music, voice
- Upload/schedule to YouTube
- Archive + monthly compilation

## Repo vs runtime
This repo tracks source + templates only.
Runtime outputs and reference corpuses are intentionally not committed:
- data/, runtime/, logs/, tmp/, reference/open5e/, reference/srd5.1/

## Structure
- bin/        core/render/upload/utils scripts
- config/     templates + configuration
- services/   systemd/nginx/docker helpers
- docs/       documentation
