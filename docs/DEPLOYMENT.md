# Deployment Guide (Umbrel)

## Production Target
- Host: 192.168.68.128
- Platform: Umbrel Home Server
- Source: GitHub (`main` branch)

## Standard Deploy Flow
1. Push tested changes from dev machine to GitHub.
2. SSH into Umbrel host.
3. Pull latest from `origin/main`.
4. Ensure dependencies are present.
5. Run daily pipeline.
6. Verify logs and outputs.

## Example Commands
Run from Umbrel shell in repo root:

```bash
git pull --rebase
python3 -m pip install --user pyyaml
export BIZZAL_ACTIVE_SRD_PATH=/home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD
bin/core/run_daily.sh
```

## Reference Corpus Alignment (Umbrel-local)
- The production SRD JSON corpus can remain local on Umbrel and outside Git.
- Pipeline scripts resolve sources in this order:
	1) `BIZZAL_ACTIVE_SRD_PATH` (or `BG_ACTIVE_SRD_PATH`)
	2) `config/reference_sources.yaml` `active_srd_path`
	3) repo fallback `reference/active`
	4) legacy fallback `reference/srd5.1`

If you want a local dev mirror from Umbrel:

```bash
rsync -av --delete \
	umbrel@192.168.68.128:/home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD/ \
	reference/srd5.1/
```

Or use the helper script from repo root (recommended):

```bash
bin/core/sync_reference_from_umbrel.sh
```

Optional explicit args:

```bash
bin/core/sync_reference_from_umbrel.sh 192.168.68.128 umbrel /home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD
```

For the Open5e v2 WotC SRD 2024 path:

```bash
bin/core/sync_reference_from_umbrel.sh 192.168.68.128 umbrel /home/umbrel/umbrel/data/reference/open5e/open5e-api/data/v2/wizards-of-the-coast/srd-2024
```

The script creates a timestamped snapshot under `reference/snapshots/`, updates `reference/active` to the latest snapshot, and mirrors to `reference/srd5.1` for backward compatibility.

Then verify:

```bash
bin/core/inventory_active_srd.py
ls -la data/reference_inventory/
```

## SRD PDF for AI Flavor/Context
- `config/reference_sources.yaml` includes `srd_pdf_path` for SRD narrative/context retrieval.
- Override via env if needed:

```bash
export BIZZAL_SRD_PDF_PATH=/home/umbrel/umbrel/data/reference/srd/SRD_CC_v5.2.1.pdf
```

- Generated atoms carry `source.srd_pdf_path` metadata so later AI stages can consume the same canonical PDF source.

## Monthly Zine Export Manifest
Generate a month-level manifest keyed by canonical content/segment IDs:

```bash
bin/core/monthly_export_manifest.py --month 2026-02
```

Outputs:
- `data/archive/monthly/YYYY-MM/manifest.json`
- `data/archive/monthly/YYYY-MM/manifest.md`

These are designed for downstream voice/image reconciliation and monthly compilation workflows.

Generate a zine-friendly content + asset pack from the manifest:

```bash
bin/core/monthly_export_pack.py --month 2026-02
```

Outputs:
- `data/archive/monthly/YYYY-MM/zine_pack/content.md`
- `data/archive/monthly/YYYY-MM/zine_pack/assets.csv`

Run the full monthly release bundle (manifest + zine pack + checks) in one command:

```bash
bin/core/monthly_release_bundle.sh 2026-02
```

For cron-safe monthly execution with timestamped logs:

```bash
bin/core/monthly_release_cron.sh 2026-02
```

This writes run logs to:
- `data/archive/monthly/YYYY-MM/logs/monthly_release_*.log`

Example crontab (run at 06:10 UTC on the 1st of each month for previous month):

```bash
10 6 1 * * cd /home/umbrel/Bizzal_Games_Pub && bin/core/monthly_release_cron.sh "$(date -d 'last month' +\%Y-\%m)"
```

## Verification Checklist
```bash
git status -sb
ls -la data/atoms/validated/
bin/core/pipeline_health_check.sh
```

Optional month-specific check:

```bash
bin/core/pipeline_health_check.sh --month 2026-02
```

Email RED/GREEN health status (SMTP):

```bash
export BIZZAL_SMTP_HOST=smtp.gmail.com
export BIZZAL_SMTP_PORT=587
export BIZZAL_SMTP_USER=bizzalgames70@gmail.com
export BIZZAL_SMTP_PASS='YOUR_APP_PASSWORD'
export BIZZAL_SMTP_STARTTLS=1
export BIZZAL_SMTP_SSL=0
export BIZZAL_ALERT_EMAIL_TO=bizzalgames70@gmail.com
export BIZZAL_ALERT_EMAIL_FROM=bizzalgames70@gmail.com

bin/core/pipeline_health_email.py --month 2026-02
```

Dry run (no email sent):

```bash
bin/core/pipeline_health_email.py --month 2026-02 --dry-run
```

Suggested cron notifications on Umbrel:

```bash
# daily status email after daily pipeline
20 9 * * * cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && export BIZZAL_SMTP_HOST=smtp.gmail.com && export BIZZAL_SMTP_PORT=587 && export BIZZAL_SMTP_USER=bizzalgames70@gmail.com && export BIZZAL_SMTP_PASS='YOUR_APP_PASSWORD' && export BIZZAL_SMTP_STARTTLS=1 && export BIZZAL_SMTP_SSL=0 && export BIZZAL_ALERT_EMAIL_TO=bizzalgames70@gmail.com && export BIZZAL_ALERT_EMAIL_FROM=bizzalgames70@gmail.com && bin/core/pipeline_health_email.py >> /home/umbrel/Bizzal_Games_Pub/logs/cron_pipeline_health_email.log 2>&1

# monthly status email after monthly release
30 6 1 * * cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && export BIZZAL_SMTP_HOST=smtp.gmail.com && export BIZZAL_SMTP_PORT=587 && export BIZZAL_SMTP_USER=bizzalgames70@gmail.com && export BIZZAL_SMTP_PASS='YOUR_APP_PASSWORD' && export BIZZAL_SMTP_STARTTLS=1 && export BIZZAL_SMTP_SSL=0 && export BIZZAL_ALERT_EMAIL_TO=bizzalgames70@gmail.com && export BIZZAL_ALERT_EMAIL_FROM=bizzalgames70@gmail.com && bin/core/pipeline_health_email.py --month "$(date -d 'last month' +\%Y-\%m)" >> /home/umbrel/Bizzal_Games_Pub/logs/cron_pipeline_health_email.log 2>&1
```

Discord webhook RED/GREEN health status (free alternative):

```bash
export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'

bin/core/pipeline_health_discord.py --month 2026-02
```

Dry run (prints webhook payload only):

```bash
bin/core/pipeline_health_discord.py --month 2026-02 --dry-run
```

Reduce noise by sending only when status changes:

```bash
bin/core/pipeline_health_discord.py --month 2026-02 --only-on-change
```

State is stored at:
- `data/archive/health/discord_state.json`

Suggested cron notifications on Umbrel (Discord):

```bash
# daily status notification after daily pipeline
20 9 * * * cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' && bin/core/pipeline_health_discord.py --only-on-change >> /home/umbrel/Bizzal_Games_Pub/logs/cron_pipeline_health_discord.log 2>&1

# monthly status notification after monthly release
30 6 1 * * cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' && bin/core/pipeline_health_discord.py --month "$(date -d 'last month' +\%Y-\%m)" --only-on-change >> /home/umbrel/Bizzal_Games_Pub/logs/cron_pipeline_health_discord.log 2>&1
```

If render/upload scripts are present and executable, `run_daily.sh` will invoke them automatically.

## Operational Notes
- Keep production changes pull-only from GitHub (avoid ad-hoc manual edits on server)
- Prefer tagged releases for rollback points
- Save service/cron details here once finalized

## Rollback (Simple)
If needed, reset to a known tag/commit:

```bash
git fetch --tags
git checkout <known-good-tag-or-commit>
```

Then run pipeline checks again before resuming schedule.
