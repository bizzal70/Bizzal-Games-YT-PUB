# Deployment Guide (Local)

This pipeline runs entirely on a single machine — no remote host, no promotion/SSH step. Code changes go straight from your local clone to GitHub via a normal commit/push.

## Production Target
- Host: your local machine (laptop)
- Source: GitHub (`main` branch), cloned locally

## Standard Run Flow
1. `git pull` to get the latest from `origin/main`.
2. Ensure dependencies are present (`python3 -m pip install -r requirements.txt`).
3. Run the daily pipeline.
4. Verify logs and outputs.

## Example Commands
Run from the repo root:

```bash
git pull --rebase
python3 -m pip install --user pyyaml
bin/core/run_daily.sh
```

## Reference Corpus Alignment
- The repo carries its own copy of the SRD JSON corpus under `reference/open5e/` and the SRD PDF under `reference/srd/` — no external host required for normal use.
- Pipeline scripts resolve sources in this order:
	1) `BIZZAL_ACTIVE_SRD_PATH` (or `BG_ACTIVE_SRD_PATH`)
	2) the `rpg_systems.active_srd_path` DB column for the current `BIZZAL_SYSTEM_ID` (see [docs/RPG_SYSTEMS.md](RPG_SYSTEMS.md))
	3) repo fallback `reference/active`
	4) legacy fallback `reference/srd5.1`

If you ever want to pull a newer/alternate corpus from a remote host (NAS, second machine, etc.), set the source via env vars and run the optional sync helper:

```bash
export BIZZAL_REFERENCE_SOURCE_HOST=your.host
export BIZZAL_REFERENCE_SOURCE_USER=youruser
export BIZZAL_REFERENCE_SOURCE_PATH=/path/to/reference/open5e/ACTIVE_WOTC_SRD
bin/core/sync_reference_from_umbrel.sh
```

The script creates a timestamped snapshot under `reference/snapshots/`, updates `reference/active` to the latest snapshot, and mirrors to `reference/srd5.1` for backward compatibility. Without those env vars set, it's a no-op — this step isn't needed for a single-machine setup.

Then verify:

```bash
bin/core/inventory_active_srd.py
ls -la data/reference_inventory/
```

## SRD PDF for AI Flavor/Context
- The `rpg_systems.srd_pdf_path` DB column (see [docs/RPG_SYSTEMS.md](RPG_SYSTEMS.md)) holds `srd_pdf_path` for SRD narrative/context retrieval.
- Defaults to the repo-relative copy (`reference/srd/SRD_CC_v5.2.1.pdf`); override via env if you keep it elsewhere:

```bash
export BIZZAL_SRD_PDF_PATH=/path/to/SRD_CC_v5.2.1.pdf
```

- Generated atoms carry `source.srd_pdf_path` metadata so later AI stages can consume the same canonical PDF source.

## SRD JSON + PDF in Git (LFS)
The SRD corpus is committed directly under `reference/`:
- `reference/open5e/` → SRD JSON fixture files
- `reference/srd/` → SRD PDF(s), including `SRD_CC_v5.2.1.pdf`

If these grow large enough to want Git LFS:

```bash
git lfs install
git lfs track "reference/open5e/**/*.json" "reference/srd/**/*.pdf"
git add .gitattributes
git add reference/open5e reference/srd
git commit -m "Track SRD JSON and PDF with LFS"
git push
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

Generate a long-form monthly video by concatenating available daily renders:

```bash
bin/core/monthly_concat_video.sh 2026-02
```

By default, this includes only days with Discord approval state `approved` or `published`
from `data/archive/approvals/discord_publish_gate.json` so long-form content follows
the same approval gate as daily publish. To disable this filter for a one-off rebuild:

```bash
BIZZAL_MONTHLY_REQUIRE_DISCORD_APPROVAL=0 bin/core/monthly_concat_video.sh 2026-02
```

Outputs:
- `data/archive/monthly/YYYY-MM/monthly_longform_YYYY-MM.mp4`
- `data/archive/monthly/YYYY-MM/monthly_longform_YYYY-MM.json`

Run the full monthly release bundle (manifest + zine pack + checks) in one command:

```bash
bin/core/monthly_release_bundle.sh 2026-02
```

For cron-safe monthly execution with timestamped logs:

```bash
bin/core/monthly_release_cron.sh 2026-02
```

Request Discord approval for monthly longform (same gate pattern as daily):

```bash
bin/core/monthly_publish_gate.py request --month 2026-02
```

Process Discord approvals and publish monthly longform when approved:

```bash
bin/core/monthly_publish_gate.py check --publish
```

Monthly private uploader (called by monthly gate check when approved):

```bash
bin/upload/upload_youtube_monthly.py --month 2026-02
```

Notes:
- Monthly uploader defaults to `private` privacy (`BIZZAL_YT_MONTHLY_PRIVACY` or `BIZZAL_YT_PRIVACY`).
- Monthly gate state file defaults to `data/archive/approvals/discord_monthly_publish_gate.json`.
- Monthly publish registry defaults to `data/archive/publish/published_monthly_registry.json`.

This writes run logs to:
- `data/archive/monthly/YYYY-MM/logs/monthly_release_*.log`

Example crontab (run at 06:10 UTC on the 1st of each month for previous month):

```bash
10 6 1 * * cd /path/to/Bizzal-Games-YT-PUB && bin/core/monthly_release_cron.sh "$(date -d 'last month' +\%Y-\%m)"
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

Suggested cron notifications:

```bash
# daily status email after daily pipeline
20 9 * * * cd /path/to/Bizzal-Games-YT-PUB && . .venv/bin/activate && export BIZZAL_SMTP_HOST=smtp.gmail.com && export BIZZAL_SMTP_PORT=587 && export BIZZAL_SMTP_USER=bizzalgames70@gmail.com && export BIZZAL_SMTP_PASS='YOUR_APP_PASSWORD' && export BIZZAL_SMTP_STARTTLS=1 && export BIZZAL_SMTP_SSL=0 && export BIZZAL_ALERT_EMAIL_TO=bizzalgames70@gmail.com && export BIZZAL_ALERT_EMAIL_FROM=bizzalgames70@gmail.com && bin/core/pipeline_health_email.py >> logs/cron_pipeline_health_email.log 2>&1

# monthly status email after monthly release
30 6 1 * * cd /path/to/Bizzal-Games-YT-PUB && . .venv/bin/activate && export BIZZAL_SMTP_HOST=smtp.gmail.com && export BIZZAL_SMTP_PORT=587 && export BIZZAL_SMTP_USER=bizzalgames70@gmail.com && export BIZZAL_SMTP_PASS='YOUR_APP_PASSWORD' && export BIZZAL_SMTP_STARTTLS=1 && export BIZZAL_SMTP_SSL=0 && export BIZZAL_ALERT_EMAIL_TO=bizzalgames70@gmail.com && export BIZZAL_ALERT_EMAIL_FROM=bizzalgames70@gmail.com && bin/core/pipeline_health_email.py --month "$(date -d 'last month' +\%Y-\%m)" >> logs/cron_pipeline_health_email.log 2>&1
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

Interactive setup (prompts for each value and persists to `~/.config/bizzal.env`):

```bash
bin/core/setup_publish_env.sh
```

One-command key validation (masked output):

```bash
bin/core/keys_health_check.sh
```

Production preflight (fails non-zero if required publish/approval env is missing):

```bash
bin/core/preflight_prod_env.sh
```

On Linux/WSL, if you've made `~/.config/bizzal.env` immutable (`chattr +i`) and updates fail (`Operation not permitted`), unlock/edit/relock:

```bash
sudo chattr -i ~/.config/bizzal.env
bin/core/setup_publish_env.sh
grep -q '^export BIZZAL_REQUIRE_DISCORD_APPROVAL=' ~/.config/bizzal.env || echo "export BIZZAL_REQUIRE_DISCORD_APPROVAL='1'" >> ~/.config/bizzal.env
sudo chattr +i ~/.config/bizzal.env
```

(`chattr` is an ext-filesystem feature and isn't available on native Windows — it's optional hardening, not required. On Windows, just edit the env file directly.)

Probe external auth endpoints (OpenAI/Replicate/Discord + YouTube file checks):

```bash
bin/core/keys_health_check.sh --probe
```

Flow:
- Daily run posts the generated script to Discord with instructions.
- Approver replies in channel: `approve YYYY-MM-DD` (or `approve <content_id>`).
- Shortcut supported: if only one pending item, reply with `Approved` (or `Rejected`).
- Approval processor publishes automatically.
- Discord posts confirmation updates: approval accepted, publish started, and publish complete/failed.

### YouTube Auto-Publish Adapter (recommended)
Uploader scripts:
- `bin/upload/upload_youtube.py`
- `bin/upload/publish_latest_youtube.sh`

One-time package install:

```bash
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

One-time YouTube OAuth setup:

```bash
mkdir -p ~/.config/bizzal
# place your Google OAuth client JSON here:
# ~/.config/bizzal/youtube_client_secrets.json
```

If Google Cloud no longer allows downloading client secret JSON, set these instead:

```bash
export BIZZAL_YT_CLIENT_ID='YOUR_OAUTH_CLIENT_ID.apps.googleusercontent.com'
export BIZZAL_YT_CLIENT_SECRET='YOUR_OAUTH_CLIENT_SECRET'
```

The uploader supports either the JSON file or these env vars.

Optional uploader env:

```bash
export BIZZAL_YT_CLIENT_SECRETS=~/.config/bizzal/youtube_client_secrets.json
export BIZZAL_YT_TOKEN_FILE=~/.config/bizzal/youtube_token.json
export BIZZAL_YT_PRIVACY=private
export BIZZAL_YT_CATEGORY_ID=20
export BIZZAL_YT_OAUTH_MODE=console
```

Refresh or repair the YouTube token without attempting an upload:

```bash
. .venv/bin/activate
bin/upload/upload_youtube.py --refresh-auth-only
```

Set publish command to stable wrapper:

```bash
export BIZZAL_PUBLISH_CMD=./bin/upload/publish_latest_youtube.sh
```

Duplicate publish protection:
- `upload_youtube.py` computes a publish fingerprint (atom content + script + day + rendered video hash)
- Fingerprints are recorded at `data/archive/publish/published_registry.json`
- Duplicate content is always blocked (no override) to prevent accidental re-publish of the same asset/script

### Incident-Proof Publish Runbook

Use this as the canonical operator flow for daily publishing.

Daily publish flow:

```bash
bin/core/preflight_prod_env.sh
bin/core/discord_publish_gate.py request --day "$(date +%F)"
# Approver posts in Discord channel: approve YYYY-MM-DD
bin/core/discord_publish_gate.py check --publish
```

`preflight_prod_env.sh` now includes a non-interactive YouTube auth probe. If token refresh is revoked, it fails early with `YOUTUBE_AUTH=INVALID_GRANT` so publish does not enter repeated `rc=9` loops.

Optional bypass (not recommended except break-glass):

```bash
export BIZZAL_PREFLIGHT_CHECK_YOUTUBE_AUTH=0
```

Expected outcomes:
- `published` → success
- `approved_publish_failed` with `publish_rc=6` → duplicate blocked (expected safety)
- `approved_publish_failed` with `publish_rc=9` → YouTube token expired or revoked; refresh auth, then retry publish
- `pending` → no valid approval message seen yet

Fast status check:

```bash
jq '.approvals | to_entries[] | {day:.key,status:.value.status,content_id:.value.content_id}' data/archive/approvals/discord_publish_gate.json | tail -n 20
```

If approval appears ignored (stuck pending):
- Re-post a **new** Discord message after the latest request timestamp:
	- `approve YYYY-MM-DD` or `approve <content_id>`
- Then run:

```bash
bin/core/discord_publish_gate.py check --publish
```

If approval already succeeded but publish failed and you fixed the cause, retry without re-requesting approval:

```bash
bin/core/discord_publish_gate.py retry --day YYYY-MM-DD
```

Recover a recent backlog across both chains:

```bash
bin/core/recover_recent_publish_backlog.sh --days 10
```

This retries any day already in `approved` or `approved_publish_failed` state. To also post Discord approval requests for historical validated days that have no approval entry yet:

```bash
bin/core/recover_recent_publish_backlog.sh --days 10 --request-missing
```

If env file update fails with `Operation not permitted` (Linux/WSL only, immutable-flagged file):

```bash
sudo chattr -i ~/.config/bizzal.env
sudo sed -i '/^BIZZAL_REQUIRE_DISCORD_APPROVAL=/d' ~/.config/bizzal.env
echo 'BIZZAL_REQUIRE_DISCORD_APPROVAL=1' | sudo tee -a ~/.config/bizzal.env >/dev/null
```

Must-pass hardening checks:

```bash
bash bin/core/preflight_prod_env.sh
grep -n 'publish blocked; Discord approval required' bin/upload/upload_youtube.py
grep -n 'Duplicate override is disabled by policy' bin/upload/upload_youtube.py
grep -n 'upload deferred: use Discord publish gate check --publish' bin/core/run_daily.sh
```

Weekly approval-state cleanup (already cron-safe):

```bash
bin/core/prune_approval_state.sh 30
```

First run will prompt OAuth and store refresh token; later runs publish directly.

Manual commands:

```bash
# send approval request for today
bin/core/discord_publish_gate.py request --day "$(date +%F)"

# process approvals and publish if approved
bin/core/discord_publish_gate.py check --publish
```

State file:
- `data/archive/approvals/discord_publish_gate.json`

Suggested cron notifications (Discord):

```bash
# daily status notification after daily pipeline
20 9 * * * cd /path/to/Bizzal-Games-YT-PUB && . .venv/bin/activate && export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' && bin/core/pipeline_health_discord.py --only-on-change >> logs/cron_pipeline_health_discord.log 2>&1

# monthly status notification after monthly release
30 6 1 * * cd /path/to/Bizzal-Games-YT-PUB && . .venv/bin/activate && export BIZZAL_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' && bin/core/pipeline_health_discord.py --month "$(date -d 'last month' +\%Y-\%m)" --only-on-change >> logs/cron_pipeline_health_discord.log 2>&1
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

Suggested weekly backup cron (Sunday 07:15 UTC):

```bash
15 7 * * 0 cd /path/to/Bizzal-Games-YT-PUB && . .venv/bin/activate && bin/core/backup_ops_config.sh >> logs/cron_ops_backup.log 2>&1
```

Prune old backup snapshots (keep latest 12):

```bash
bin/core/prune_ops_backups.sh --keep 12
```

Dry run preview:

```bash
bin/core/prune_ops_backups.sh --keep 12 --dry-run
```

Suggested monthly cleanup cron (day 1 at 07:25 UTC):

```bash
25 7 1 * * cd /path/to/Bizzal-Games-YT-PUB && . .venv/bin/activate && bin/core/prune_ops_backups.sh --keep 12 >> logs/cron_ops_backup.log 2>&1
```

If render/upload scripts are present and executable, `run_daily.sh` will invoke them automatically.

Render pacing notes:
- `bin/render/render_atom.sh` now uses dynamic timing for hook/body/cta based on word counts (instead of fixed 10/10/10).
- CTA timing is category-aware:
	- `encounter_seed`, `monster_tactic` → slightly longer CTA window.
	- `rules_ruling`, `rules_myth` → compact CTA window.
	- `spell_use_case`, `item_spotlight`, `character_micro_tip` → balanced CTA window.
- Optional override: `BIZZAL_SHORTS_DURATION` (default `30`).
- Body text flow controls (to avoid short → wall → short cadence):
	- `BIZZAL_BODY_MAXLINES` (default `7`) lines per body page before repagination.
	- `BIZZAL_BODY_MAX_PAGES` (default `3`) caps body page count for readability.
	- `BIZZAL_BODY_LAST_MIN_WORDS` (default `5`) merges tiny final orphan page into previous page.
	- `BIZZAL_BODY_PAGE_MIN_SEC` (default `4`) minimum seconds shown per body page.
	- `BIZZAL_PAGE_XFADE_SEC` (default `0.15`) subtle crossfade between body pages.
	- `BIZZAL_CTA_FINAL_HOLD_SEC` (default `0.30`) extra final CTA hold at end of render.

Example:

```bash
BIZZAL_SHORTS_DURATION=30 bin/render/render_atom.sh 2026-02-13
```

Tone/flavor-aware TTS voice selection:
- `bin/core/pick_style.py` now selects `style.voiceover.tts_voice_id` from the DB-backed config using tone + style voice (see [docs/RPG_SYSTEMS.md](RPG_SYSTEMS.md)).
- Configure tone-level pools in the `system_tones` table.
- Optionally override by style voice via `system_voices.tts_voice_ids`.
- Selection is deterministic per `day|category|tone|voice`, so reruns stay stable while still varying across script flavors.

## Optional: TTS Narration in Render Output
`bin/render/render_atom.sh` can now synthesize narration and mux it into the final MP4.

Environment flags:
- `BIZZAL_ENABLE_TTS=1` enables TTS synthesis/mux during render.
- `OPENAI_API_KEY` (or `BIZZAL_OPENAI_API_KEY`) must be set to a valid key.
- Optional: `BIZZAL_TTS_MODEL` (default: `gpt-4o-mini-tts`).
- Optional: `BIZZAL_TTS_SPEED` speaking pace (default: `1.0`, valid range `0.25-4.0`).
- Optional: `BIZZAL_TTS_TIMING_MODE` (`per_screen` default, `off` to disable per-screen timing sync).
- Optional: `BIZZAL_TTS_BODY_PAGE_MIN_SEC` minimum body page hold in per-screen sync mode (default: `5`).
- Optional: `BIZZAL_OPENAI_TTS_ENDPOINT` (default: `https://api.openai.com/v1/audio/speech`).

Outputs when enabled:
- `data/renders/by_day/YYYY-MM-DD.voice.wav`
- `data/renders/latest/latest.voice.wav`

Example:

```bash
export OPENAI_API_KEY='YOUR_OPENAI_API_KEY'
export BIZZAL_ENABLE_TTS=1
export BIZZAL_TTS_SPEED=0.92
BIZZAL_TEXT_STYLE=bg_safe bin/render/render_atom.sh 2026-02-13
```

Speed tips:
- `0.88-0.95` = calmer / more deliberate narration
- `1.00` = neutral default
- `1.05-1.15` = snappier pacing

If TTS fails (missing key/API error), render falls back to text-only MP4 and logs the reason.

## Optional: AI Background Music (Replicate)
`bin/render/render_atom.sh` can generate tone/topic-aware background music and mix it under narration.

## Optional: AI Background Imagery (Replicate)
`bin/render/render_atom.sh` can generate a tone/topic-aware background image from the daily atom and use it behind on-screen text.

Environment flags:
- `BIZZAL_ENABLE_BG_IMAGE=1` enables AI background image generation.
- `REPLICATE_API_TOKEN` required for Replicate calls.
- Optional: `BIZZAL_BG_IMAGE_MODE` (`single` default in base renderer, `per_screen` to generate hook/body/cta images and transition between them).
- Optional: `BIZZAL_BG_IMAGE_XFADE_SEC` crossfade duration between per-screen images (default `0.40` in base renderer).
- Optional: `BIZZAL_BG_IMAGE_MOTION=1` enables subtle cinematic pan drift on background images.
- Optional: `BIZZAL_BG_IMAGE_MOTION_PIXELS` drift amplitude in pixels (default `26` in base renderer).
- Optional: `BIZZAL_BG_IMAGE_MOTION_SPEED` drift speed (default `0.22` in base renderer).
- Optional: `BIZZAL_REPLICATE_IMAGE_MODEL` (default: `black-forest-labs/flux-schnell`; script auto-falls back across known image slugs).
- Optional: `BIZZAL_BG_IMAGE_ASPECT_RATIO` (default `9:16`).
- Optional: `BIZZAL_BG_IMAGE_FORMAT` (default `png`).
- Optional post-processing tone controls:
	- `BIZZAL_BG_IMAGE_BRIGHTNESS` (default `-0.10`)
	- `BIZZAL_BG_IMAGE_SATURATION` (default `0.90`)
	- `BIZZAL_BG_IMAGE_CONTRAST` (default `1.02`)

Outputs when enabled:
- `data/renders/by_day/YYYY-MM-DD.bg.png`
- `data/renders/latest/latest.bg.png`

If image generation fails, render falls back gracefully to solid background and still produces MP4 output.

House preset (one command):

```bash
bin/render/run_house_render.sh
```

Optional specific day:

```bash
bin/render/run_house_render.sh 2026-02-13
```

This wrapper applies your production defaults (per-screen AI background images + smooth image transitions, cinematic audio profile, TTS+music on, tuned ducking/tone, and music fade-out tail) and then runs `render_atom.sh`.

House preset timing defaults:
- `BIZZAL_INTRO_PAD_SEC=2`
- `BIZZAL_INTRO_FADE_SEC=2`
- `BIZZAL_END_FADE_SEC=4`
- `BIZZAL_END_BLACK_PAD_SEC=2`

Environment flags:
- `BIZZAL_ENABLE_BG_MUSIC=1` enables music generation and mixing.
- `REPLICATE_API_TOKEN` required for Replicate calls.
- Optional: `BIZZAL_REPLICATE_MUSIC_MODEL` (default: `stability-ai/stable-audio-2.5`; script auto-falls back across known music slugs if one is unavailable).
- Optional: `BIZZAL_REPLICATE_MUSIC_VERSION` (pin if model-level calls are restricted on your account).
- Optional: `BIZZAL_BG_MUSIC_SECONDS` (default uses current render duration).
- Optional: `BIZZAL_BG_MUSIC_INCLUDE_DURATION=1` (off by default; enables `duration/seconds` input fields for models that require them).
- Optional: `BIZZAL_BG_MUSIC_TAIL_SEC` (default `3`; extends outro with music-only fade while screen fades to black).
- Optional: `BIZZAL_INTRO_PAD_SEC` (default `0` in base renderer; prepends black before content starts).
- Optional: `BIZZAL_INTRO_FADE_SEC` (default `0`; fades from black into content after intro pad).
- Optional: `BIZZAL_END_FADE_SEC` (default `0`; fade-out duration at close).
- Optional: `BIZZAL_END_BLACK_PAD_SEC` (default `0`; hold-on-black duration after fade-out).
- Optional: `BIZZAL_TEXT_BOTTOM_PAD` (default `250`; moves text block up from bottom while keeping bottom-centered layout).
- Optional: `BIZZAL_AUDIO_PROFILE=cinematic` (warmer/wider defaults and gentler ducking).
- Optional: `BIZZAL_FINAL_LOUDNORM=1` (default on; normalizes final loudness for more consistent playback).
- Optional: `BIZZAL_BG_MUSIC_GAIN` (default `0.42`, when TTS is present).
- Optional: `BIZZAL_BG_MUSIC_GAIN_NO_VO` (default `0.32`, when no TTS voice track).
- Optional ducking controls:
	- `BIZZAL_BG_DUCK_THRESHOLD` (default `0.10`)
	- `BIZZAL_BG_DUCK_RATIO` (default `2.0`)
	- `BIZZAL_BG_DUCK_ATTACK_MS` (default `25`)
	- `BIZZAL_BG_DUCK_RELEASE_MS` (default `550`)
- Optional music tone/widening controls:
	- `BIZZAL_BG_TONE_LOWCUT_HZ` (default `45`)
	- `BIZZAL_BG_TONE_HIGHCUT_HZ` (default `14500`)
	- `BIZZAL_BG_TONE_WARMTH_DB` (default `2.5`)
	- `BIZZAL_BG_TONE_PRESENCE_DB` (default `-2.0`)
	- `BIZZAL_BG_MONO_WIDEN_MS` (default `14`, used when source music is mono)

Outputs when enabled:
- `data/renders/by_day/YYYY-MM-DD.music.wav`
- `data/renders/latest/latest.music.wav`

Example:

```bash
export REPLICATE_API_TOKEN='YOUR_REPLICATE_TOKEN'
export BIZZAL_ENABLE_BG_MUSIC=1
export BIZZAL_AUDIO_PROFILE=cinematic
export BIZZAL_BG_MUSIC_GAIN=0.50
export BIZZAL_BG_DUCK_RATIO=1.8
BIZZAL_TEXT_STYLE=bg_safe bin/render/render_atom.sh 2026-02-13
```

If music generation fails, render falls back gracefully and still produces MP4 output.

Render preview link echo (enabled by default):
- `BIZZAL_ECHO_PREVIEW_URL=1` prints direct test links after each render.
- `BIZZAL_PREVIEW_HOST` sets the host/IP in printed links (default `localhost`).
- `BIZZAL_PREVIEW_PORT` sets the port in printed links (default `8766`).

Replicate 403 quick triage:

```bash
# 1) token sanity
curl -sS -H "Authorization: Token $REPLICATE_API_TOKEN" https://api.replicate.com/v1/account | head

# 2) prediction endpoint permission check (422 means endpoint is reachable/auth works)
curl -sS -o /tmp/replicate_pred_probe.json -w "HTTP %{http_code}\n" \
	-H "Authorization: Token $REPLICATE_API_TOKEN" \
	-H "Content-Type: application/json" \
	-d '{"version":"0000000000000000000000000000000000000000000000000000000000000000","input":{"prompt":"probe"}}' \
	https://api.replicate.com/v1/predictions
cat /tmp/replicate_pred_probe.json
```

Interpretation:
- `HTTP 422` = auth/path is okay; pick a model/version your account can run.
- `HTTP 403` = account/model permission or billing restriction; update Replicate plan/permissions first.

## Optional: AI Script Smoothing (OpenAI)
`write_script_from_fact.py` can optionally polish language with OpenAI while keeping deterministic fallback templates.

One-command diagnostic daily run (loads `.env.ai`, enables AI/debug flags, writes `/tmp` log):

```bash
bin/core/run_daily_diag.sh
```

Optional log dir override:

```bash
BIZZAL_DAILY_LOG_DIR=logs bin/core/run_daily_diag.sh
```

Cron-safe diagnostic wrapper (timestamped logs, preserves exit code):

```bash
bin/core/run_daily_diag_cron.sh
```

Optional cron log dir override:

```bash
BIZZAL_DAILY_CRON_LOG_DIR=logs bin/core/run_daily_diag_cron.sh
```

> **Windows note:** `crontab` and the installer below require a `cron` daemon, which native Windows doesn't have. Either run these scripts inside WSL (where `crontab` works normally), or schedule `bin/core/run_daily_diag_cron.sh` etc. via **Windows Task Scheduler** instead (`schtasks /create ...` or the Task Scheduler GUI), pointing it at a shell capable of running these `.sh` scripts (Git Bash or WSL).

Suggested daily cron (8:00 PM Mountain):

```bash
CRON_TZ=America/Denver
0 20 * * * cd /path/to/Bizzal-Games-YT-PUB && bin/core/run_daily_diag_cron.sh
```

One-command cron automation installer (idempotent, Linux/WSL only):

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

Suggested weekly prune cron (Sunday 8:20 PM Mountain):

```bash
CRON_TZ=America/Denver
20 20 * * 0 cd /path/to/Bizzal-Games-YT-PUB && bin/core/prune_daily_diag_logs.sh --keep-days 30
```

Current behavior:
- `BIZZAL_ENABLE_AI=1` enables CTA-only polishing.
- `BIZZAL_ENABLE_AI_SCRIPT=1` enables Hook+Body+CTA polishing (recommended for more personal tone).
- If API is unavailable, generation falls back to deterministic templates automatically.
- `source.srd_pdf_path` is recorded in atoms for provenance, but no direct PDF text retrieval stage is active yet.

Enable before running the daily pipeline:

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
- Category personas and tones are configured in the `system_categories` / `system_tones` DB tables (see [docs/RPG_SYSTEMS.md](RPG_SYSTEMS.md)).
- `pick_style.py` assigns `style.persona`, `style.tone`, and `style.voiceover` (`voice_pack_id`, `tts_voice_id`).
- `content.asset_contract` carries `voice_pack_id` and `tts_voice_id` for future TTS voice selection.

Low-DC humor lane (optional):
- `BIZZAL_ENABLE_LOW_DC_HUMOR=1` (default) adds playful framing for low-threat creature picks, low-level/low-DC spells, and mundane items.
- It keeps tactical guidance but shifts tone so weaker picks feel intentional, not awkward.

## Operational Notes
- Commit changes to git regularly so you always have a rollback point
- Prefer tagged releases for marking known-good states
- Save service/cron details here once finalized

## Rollback (Simple)
If needed, reset to a known tag/commit:

```bash
git fetch --tags
git checkout <known-good-tag-or-commit>
```

Then run pipeline checks again before resuming schedule.
