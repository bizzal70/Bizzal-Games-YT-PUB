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

## Commit SRD JSON + PDF to GitHub (LFS)
If you want the full SRD corpus available directly in this repo for development/testing, use Git LFS and commit the canonical datasets under `reference/`.

Required layout in repo:
- `reference/open5e/` → SRD JSON fixture files
- `reference/srd/` → SRD PDF(s), including `SRD_CC_v5.2.1.pdf`

One-time setup:

```bash
git lfs install
git lfs track "reference/open5e/**/*.json" "reference/srd/**/*.pdf"
git add .gitattributes
```

Umbrel copy/paste import + push (adjust source paths if needed):

```bash
cd /home/umbrel/Bizzal_Games_Pub
git pull --ff-only
mkdir -p reference/open5e reference/srd
rsync -av --delete /home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD/ reference/open5e/
cp -f /home/umbrel/umbrel/data/reference/srd/SRD_CC_v5.2.1.pdf reference/srd/SRD_CC_v5.2.1.pdf
git add .gitattributes .gitignore reference/open5e reference/srd docs/DEPLOYMENT.md
git commit -m "Vendor SRD JSON and PDF into reference/ with LFS"
git push
```

After this, set runtime path to the committed corpus if desired:

```bash
export BIZZAL_ACTIVE_SRD_PATH=/home/umbrel/Bizzal_Games_Pub/reference/open5e
export BIZZAL_SRD_PDF_PATH=/home/umbrel/Bizzal_Games_Pub/reference/srd/SRD_CC_v5.2.1.pdf
```

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

Force a notification even if status is unchanged:

```bash
bin/core/pipeline_health_discord.py --month 2026-02 --only-on-change --force-send
```

State is stored at:
- `data/archive/health/discord_state.json`

## Discord Approval Gate (Reply `approve` to publish)
You can require daily Discord approval before publish/upload.

Environment variables:

```bash
export BIZZAL_REQUIRE_DISCORD_APPROVAL=1
export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
export BIZZAL_DISCORD_BOT_TOKEN='YOUR_DISCORD_BOT_TOKEN'
export BIZZAL_DISCORD_CHANNEL_ID='YOUR_CHANNEL_ID'
export BIZZAL_DISCORD_APPROVER_USER_IDS='123456789012345678,234567890123456789'
```

Flow:
- Daily run posts the generated script to Discord with instructions.
- Approver replies in channel: `approve YYYY-MM-DD` (or `approve <content_id>`).
- Approval processor publishes automatically.
- Discord posts confirmation updates: approval accepted, publish started, and publish complete/failed.

Manual commands:

```bash
# send approval request for today
bin/core/discord_publish_gate.py request --day "$(date +%F)"

# process approvals and publish if approved
bin/core/discord_publish_gate.py check --publish
```

State file:
- `data/archive/approvals/discord_publish_gate.json`

Suggested cron notifications on Umbrel (Discord):

```bash
# daily status notification after daily pipeline
20 9 * * * cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' && bin/core/pipeline_health_discord.py --only-on-change >> /home/umbrel/Bizzal_Games_Pub/logs/cron_pipeline_health_discord.log 2>&1

# monthly status notification after monthly release
30 6 1 * * cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' && bin/core/pipeline_health_discord.py --month "$(date -d 'last month' +\%Y-\%m)" --only-on-change >> /home/umbrel/Bizzal_Games_Pub/logs/cron_pipeline_health_discord.log 2>&1
```

## Ops Backup (Cron + Alert Config)
Create a disaster-recovery snapshot of current crontab and alert env configs (secrets redacted):

```bash
bin/core/backup_ops_config.sh
```

Output folder pattern:
- `docs/ops_backups/YYYYMMDDTHHMMSSZ/`

Contents:
- `crontab.txt`
- `env.discord_health.redacted` (if present)
- `env.health_mail.redacted` (if present)
- `README.txt` (restore notes + git SHA)

Optional custom output directory:

```bash
bin/core/backup_ops_config.sh --out-dir docs/ops_backups
```

Restore cron from a snapshot:

```bash
crontab docs/ops_backups/YYYYMMDDTHHMMSSZ/crontab.txt
```

Suggested weekly backup cron on Umbrel (Sunday 07:15 UTC):

```bash
15 7 * * 0 cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && bin/core/backup_ops_config.sh >> /home/umbrel/Bizzal_Games_Pub/logs/cron_ops_backup.log 2>&1
```

Prune old backup snapshots (keep latest 12):

```bash
bin/core/prune_ops_backups.sh --keep 12
```

Dry run preview:

```bash
bin/core/prune_ops_backups.sh --keep 12 --dry-run
```

Suggested monthly cleanup cron on Umbrel (day 1 at 07:25 UTC):

```bash
25 7 1 * * cd /home/umbrel/Bizzal_Games_Pub && . /home/umbrel/Bizzal_Games_Pub/.venv/bin/activate && bin/core/prune_ops_backups.sh --keep 12 >> /home/umbrel/Bizzal_Games_Pub/logs/cron_ops_backup.log 2>&1
```

If render/upload scripts are present and executable, `run_daily.sh` will invoke them automatically.

Render pacing notes:
- `bin/render/render_atom.sh` now uses dynamic timing for hook/body/cta based on word counts (instead of fixed 10/10/10).
- CTA timing is category-aware:
	- `encounter_seed`, `monster_tactic` → slightly longer CTA window.
	- `rules_ruling`, `rules_myth` → compact CTA window.
	- `spell_use_case`, `item_spotlight`, `character_micro_tip` → balanced CTA window.
- Optional override: `BIZZAL_SHORTS_DURATION` (default `30`).

Example:

```bash
BIZZAL_SHORTS_DURATION=30 bin/render/render_atom.sh 2026-02-13
```

Tone/flavor-aware TTS voice selection:
- `bin/core/pick_style.py` now selects `style.voiceover.tts_voice_id` from config using tone + style voice.
- Configure tone-level pools in `config/style_rules.yaml` under `voiceover_by_tone.<tone>.tts_voice_ids`.
- Optionally override by style voice under `voiceover_by_voice.<voice>.tts_voice_ids`.
- Selection is deterministic per `day|category|tone|voice`, so reruns stay stable while still varying across script flavors.

## Optional: TTS Narration in Render Output
`bin/render/render_atom.sh` can now synthesize narration and mux it into the final MP4.

Environment flags:
- `BIZZAL_ENABLE_TTS=1` enables TTS synthesis/mux during render.
- `OPENAI_API_KEY` (or `BIZZAL_OPENAI_API_KEY`) must be set to a valid key.
- Optional: `BIZZAL_TTS_MODEL` (default: `gpt-4o-mini-tts`).
- Optional: `BIZZAL_OPENAI_TTS_ENDPOINT` (default: `https://api.openai.com/v1/audio/speech`).

Outputs when enabled:
- `data/renders/by_day/YYYY-MM-DD.voice.wav`
- `data/renders/latest/latest.voice.wav`

Example:

```bash
export OPENAI_API_KEY='YOUR_OPENAI_API_KEY'
export BIZZAL_ENABLE_TTS=1
BIZZAL_TEXT_STYLE=bg_safe bin/render/render_atom.sh 2026-02-13
```

If TTS fails (missing key/API error), render falls back to text-only MP4 and logs the reason.

## Optional: AI Script Smoothing (OpenAI)
`write_script_from_fact.py` can optionally polish language with OpenAI while keeping deterministic fallback templates.

One-command diagnostic daily run (loads `.env.ai`, enables AI/debug flags, writes `/tmp` log):

```bash
bin/core/run_daily_diag.sh
```

Optional log dir override:

```bash
BIZZAL_DAILY_LOG_DIR=/home/umbrel/Bizzal_Games_Pub/logs bin/core/run_daily_diag.sh
```

Cron-safe diagnostic wrapper (timestamped logs, preserves exit code):

```bash
bin/core/run_daily_diag_cron.sh
```

Optional cron log dir override:

```bash
BIZZAL_DAILY_CRON_LOG_DIR=/home/umbrel/Bizzal_Games_Pub/logs bin/core/run_daily_diag_cron.sh
```

Suggested daily cron on Umbrel (8:00 PM Mountain):

```bash
CRON_TZ=America/Denver
0 20 * * * cd /home/umbrel/Bizzal_Games_Pub && bin/core/run_daily_diag_cron.sh
```

One-command cron automation installer (idempotent):

```bash
bin/core/install_cron_automation.sh
```

Dry-run preview:

```bash
bin/core/install_cron_automation.sh --dry-run
```

Remove the managed automation cron block:

```bash
bin/core/uninstall_cron_automation.sh
```

Uninstall dry-run preview:

```bash
bin/core/uninstall_cron_automation.sh --dry-run
```

This installs/updates one managed cron block with:
- `CRON_TZ=America/Denver` local-time scheduling
- daily `run_daily_diag_cron.sh` (8:00 PM Mountain)
- weekly `prune_daily_diag_logs.sh --keep-days 30` (Sunday 8:20 PM Mountain)
- monthly `monthly_release_cron.sh "$(date -d 'last month' +%Y-%m)"` (1st at 8:10 PM Mountain)

Optional schedule overrides (before running installer):

```bash
export BIZZAL_AUTOMATION_CRON_TZ=America/Denver
export BIZZAL_AUTOMATION_DAILY_HOUR=20
export BIZZAL_AUTOMATION_DAILY_MIN=0
export BIZZAL_AUTOMATION_WEEKLY_DAY=0
export BIZZAL_AUTOMATION_WEEKLY_HOUR=20
export BIZZAL_AUTOMATION_WEEKLY_MIN=20
export BIZZAL_AUTOMATION_MONTHLY_DAY=1
export BIZZAL_AUTOMATION_MONTHLY_HOUR=20
export BIZZAL_AUTOMATION_MONTHLY_MIN=10
bin/core/install_cron_automation.sh
```

Prune old daily diagnostic logs (default keep: 30 days):

```bash
bin/core/prune_daily_diag_logs.sh
```

Dry run preview:

```bash
bin/core/prune_daily_diag_logs.sh --keep-days 30 --dry-run
```

Suggested weekly prune cron on Umbrel (Sunday 8:20 PM Mountain):

```bash
CRON_TZ=America/Denver
20 20 * * 0 cd /home/umbrel/Bizzal_Games_Pub && bin/core/prune_daily_diag_logs.sh --keep-days 30
```

Current behavior:
- `BIZZAL_ENABLE_AI=1` enables CTA-only polishing.
- `BIZZAL_ENABLE_AI_SCRIPT=1` enables Hook+Body+CTA polishing (recommended for more personal tone).
- If API is unavailable, generation falls back to deterministic templates automatically.
- `source.srd_pdf_path` is recorded in atoms for provenance, but no direct PDF text retrieval stage is active yet.

Enable on Umbrel shell before running daily pipeline:

```bash
export BIZZAL_ENABLE_AI=1
export BIZZAL_ENABLE_AI_SCRIPT=1
export BIZZAL_ENABLE_PDF_FLAVOR=1
export BIZZAL_REQUIRE_PDF_FLAVOR=0
export OPENAI_API_KEY='YOUR_OPENAI_API_KEY'
export BIZZAL_OPENAI_MODEL='gpt-4o-mini'
```

For PDF flavor extraction, install optional dependency:

```bash
python3 -m pip install pypdf
```

Optional overrides:

```bash
export BIZZAL_OPENAI_API_KEY='YOUR_OPENAI_API_KEY'
export BIZZAL_OPENAI_ENDPOINT='https://api.openai.com/v1/chat/completions'
```

If API is unavailable or disabled, pipeline falls back to deterministic CTA templates automatically.

PDF flavor strict mode:
- Recommended default: `BIZZAL_REQUIRE_PDF_FLAVOR=0` (best-effort). AI polishing still runs even when no PDF snippet is found.
- `BIZZAL_REQUIRE_PDF_FLAVOR=1` forces AI polishing to use a found PDF snippet for the current fact.
- In strict mode, if no snippet is found (or PDF/pypdf is unavailable), AI polishing is skipped and deterministic script text is kept.
- Check logs for `PDF flavor snippet used ...` and `missing PDF flavor grounding` diagnostics.

Numeric lock mode:
- Recommended default: `BIZZAL_REQUIRE_NUMERIC_LOCK=0` (best-effort). Missing numeric tokens in AI rewrites are allowed with a warning.
- Optional strict mode: `BIZZAL_REQUIRE_NUMERIC_LOCK=1` rejects AI script rewrites that drop locked numeric tokens.

Persona/tone/voiceover routing:
- Category personas and tones are configured in `config/style_rules.yaml`.
- `pick_style.py` assigns `style.persona`, `style.tone`, and `style.voiceover` (`voice_pack_id`, `tts_voice_id`).
- `content.asset_contract` carries `voice_pack_id` and `tts_voice_id` for future TTS voice selection.

Low-DC humor lane (optional):
- `BIZZAL_ENABLE_LOW_DC_HUMOR=1` (default) adds playful framing for low-threat creature picks, low-level/low-DC spells, and mundane items.
- It keeps tactical guidance but shifts tone so weaker picks feel intentional, not awkward.

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
