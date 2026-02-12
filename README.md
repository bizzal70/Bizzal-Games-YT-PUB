# Bizzal-Games-YT-PUB

Umbrel-hosted automated “content press” for Bizzal Games.

## First day setup

```bash
git clone https://github.com/bizzal70/Bizzal-Games-YT-PUB.git
cd Bizzal-Games-YT-PUB
python3 -m pip install --user pyyaml
bin/core/run_daily.sh
```

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

## Quickstart

From the repo root:

1) Install required Python package

```bash
python3 -m pip install --user pyyaml
```

2) Run the daily pipeline

```bash
bin/core/run_daily.sh
```

The runner will:
- create and validate the daily atom
- run render step only if a render script exists
- run upload step only if an upload script exists

Useful checks:

```bash
git status -sb
ls -la data/atoms/validated/
```

## Git sync workflow

From the repo root:

```bash
git pull --rebase
# make your changes
git add .
git commit -m "describe your change"
git push
```

If you only changed one file, prefer adding it explicitly:

```bash
git add README.md
```

## Changelog

- v0.1-docs: baseline documentation release (first-day setup, quickstart, and git sync workflow)
- v0.1.1-docs: added README release-note/changelog update for docs tags

## Version tags

- v0.1-docs
- v0.1.1-docs
- v0.1.2-docs
