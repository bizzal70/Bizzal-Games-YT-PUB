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

## Reference data (Umbrel vs GitHub)

The full SRD JSON corpus can stay local-only on Umbrel and does not need to be committed.

- Default lookup path is `reference/srd5.1` (repo-relative).
- You can override at runtime with `BIZZAL_ACTIVE_SRD_PATH` (or `BG_ACTIVE_SRD_PATH`).

Example (Umbrel):

```bash
export BIZZAL_ACTIVE_SRD_PATH=/home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD
bin/core/run_daily.sh
```

For local testing with the same corpus, sync it from Umbrel into this workspace:

```bash
bin/core/sync_reference_from_umbrel.sh
```

This creates a timestamped snapshot under `reference/snapshots/`, updates `reference/active`, mirrors `reference/srd5.1/` (legacy compatibility), and regenerates reference inventory artifacts.

## Structure
- bin/        core/render/upload/utils scripts
- config/     templates + configuration
- services/   systemd/nginx/docker helpers
- docs/       documentation

## Promotion workflow
- Use the dev→GitHub→Umbrel promotion process in [docs/PROMOTION_RUNBOOK.md](docs/PROMOTION_RUNBOOK.md).

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

## On-call quick commands

Primary runbook:
- docs/DEPLOYMENT.md (Incident-Proof Publish Runbook section)

Use these on Umbrel:

```bash
cd /home/umbrel/Bizzal_Games_Pub
bash bin/core/preflight_prod_env.sh
bin/core/discord_publish_gate.py request --day "$(date +%F)"
# In Discord approval channel: approve YYYY-MM-DD
bin/core/discord_publish_gate.py check --publish
```

Fast status check:

```bash
cd /home/umbrel/Bizzal_Games_Pub
jq '.approvals | to_entries[] | {day:.key,status:.value.status,content_id:.value.content_id}' data/archive/approvals/discord_publish_gate.json | tail -n 20
```

Status meanings:
- `pending` → waiting for a valid Discord approver message after request timestamp.
- `published` → approval accepted and publish completed successfully.
- `approved_publish_failed` → approval accepted but publish failed.

Common recovery paths:
- `publish_rc=6` → duplicate blocked by policy.
- `publish_rc=9` → YouTube token expired or revoked; refresh auth, then retry publish.

Umbrel auth refresh without uploading:

```bash
cd /home/umbrel/Bizzal_Games_Pub
. .venv/bin/activate
bin/upload/upload_youtube.py --refresh-auth-only
```

Non-interactive auth probe (safe for cron/preflight):

```bash
cd /home/umbrel/Bizzal_Games_Pub
BIZZAL_YT_NONINTERACTIVE=1 bin/upload/upload_youtube.py --refresh-auth-only
```

Retry a previously approved day after fixing the root cause:

```bash
cd /home/umbrel/Bizzal_Games_Pub
bin/core/discord_publish_gate.py retry --day YYYY-MM-DD
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

Dev/Prod sync check (run from dev machine with SSH access):

```bash
cd /home/bizzal/Bizzal_Games_Pub
echo "DEV  $(git rev-parse HEAD)"
echo "ORIGIN $(git rev-parse origin/main)"
ssh umbrel@192.168.68.128 'cd /home/umbrel/Bizzal_Games_Pub && echo "PROD $(git rev-parse HEAD)" && git status -sb | head -n 1'
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
