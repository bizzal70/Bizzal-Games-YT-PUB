# Cloud v2 — running the pipeline on GitHub Actions

The daily pipeline runs in the cloud on **GitHub Actions** — no laptop or home
server required. Each day it generates the day's content atom, renders the
vertical Short, and publishes it to YouTube **straight through** (no Discord
approval step), then commits its publish-safety state back to the repo.

This repo is **public**, so Actions minutes are free and unlimited. The only
per-run costs are OpenAI + Replicate API usage (same as the local setup);
Supabase stays on the free tier.

## How it works

```
.github/workflows/daily.yml  (cron 8am America/Denver, DST-safe; + manual button)
  └─ ubuntu runner:
       checkout (full history)
       → setup Python 3.12 + ffmpeg + pip install -r requirements.txt
       → write YouTube OAuth token from a secret
       → bin/core/run_daily_cloud_cron.sh
            ├─ pick today's active system(s)            (system_config + rotation)
            ├─ run_daily_for_system.sh <id>             (generate → render → autopublish)
            └─ archive_render_to_storage.sh <id>        (MP4 → Supabase Storage, non-fatal)
       → commit data/state/** back to main  ([skip ci])
```

Key pieces:

- **No Discord gate.** `bin/core/discord_publish_gate.py autopublish` publishes
  directly, reusing the same publish-dedup registry as the old approval path,
  so a re-run never double-uploads. The Discord approval scripts still exist
  for local use.
- **Safety state survives ephemeral runners** by living in committed JSON under
  `data/state/` (`published_registry_<system>.json`,
  `style_history_<system>.json`, `publish_gate_<system>.json`). The workflow's
  last step commits any changes back to `main` with `[skip ci]`.
- **DB access from CI** uses the Supabase **IPv4 session pooler** (the direct
  DB host is IPv6-only and GitHub runners have no IPv6). `BIZZAL_DB_URL` must
  be the us-west-2 pooler string (see secrets below).

## Safety net: unlisted by default

With the human approval step removed, uploads default to **`unlisted`**
(`BIZZAL_YT_PRIVACY`). Videos publish automatically but aren't fully public
until you flip them to `public` in YouTube Studio. Change the default by
setting `BIZZAL_YT_PRIVACY` (`unlisted` | `private` | `public`) — either as a
repo variable or per-run via the manual trigger.

## Required GitHub Actions secrets

Add these under **Settings → Secrets and variables → Actions → New repository
secret**:

| Secret | What it is |
|---|---|
| `BIZZAL_DB_URL` | Supabase **session pooler** string: `postgresql://postgres.nlywxefvpibkqfctgmty:<password>@aws-0-us-west-2.pooler.supabase.com:5432/postgres` (try `aws-1-` if `aws-0-` fails) |
| `BIZZAL_OPENAI_API_KEY` | OpenAI key (script polish + TTS) |
| `BIZZAL_REPLICATE_API_TOKEN` | Replicate token (background art + music) |
| `BIZZAL_YT_CLIENT_ID` | YouTube OAuth client id |
| `BIZZAL_YT_CLIENT_SECRET` | YouTube OAuth client secret |
| `BIZZAL_YT_TOKEN_JSON` | The full authorized-user token JSON (contains the refresh token). The workflow writes it to a file and `upload_youtube.py` refreshes the access token each run. |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key (render archival to Storage) |
| `SUPABASE_URL` | `https://nlywxefvpibkqfctgmty.supabase.co` |

Discord secrets are **not** needed for the daily cloud path.

### Generating `BIZZAL_YT_TOKEN_JSON`

On a machine with Python + the repo set up, run an interactive auth once:

```bash
BIZZAL_YT_CLIENT_ID=... BIZZAL_YT_CLIENT_SECRET=... \
  python bin/upload/upload_youtube.py --refresh-auth-only
```

This writes `~/.config/bizzal/youtube_token.json` (path configurable via
`BIZZAL_YT_TOKEN_FILE`). Paste that file's entire contents into the
`BIZZAL_YT_TOKEN_JSON` secret.

## One-time Supabase Storage setup

Create a private bucket named `renders` (Dashboard → Storage → New bucket).
Archival is non-fatal: if the bucket or `SUPABASE_SERVICE_ROLE_KEY` is missing,
the run still succeeds (publishing already happened). Add a periodic prune to
stay under the 1 GB free tier.

## Running it

- **Scheduled:** fires automatically at 8am America/Denver. The two cron lines
  (14:00 + 15:00 UTC) cover MST/MDT; a guard step runs only the one that is
  actually 08:00 in Denver and no-ops the other.
- **Manual / smoke test:** Actions tab → "Daily content pipeline" → **Run
  workflow**. Inputs:
  - `systems` — `auto` (daily rotation), `all`, or a specific id (`dnd5e`)
  - `privacy` — `unlisted` | `private` | `public`
  - `dry_run` — `true` to generate + render but **skip the YouTube upload**

## Verifying

1. **Dry run:** trigger manually with `dry_run=true`, `privacy=private`.
   Confirm the logs show atom generation, render, and DB reads succeeding, and
   that the safety-state commit step runs.
2. **First real run:** trigger with `privacy=unlisted`. Confirm one unlisted
   video appears on the channel and `data/state/published_registry_*.json` got
   committed back.
3. **Dedup:** trigger again immediately for the same system/day — it should
   skip the upload (already in the registry).
4. **Schedule/DST:** check that the off-hour cron logs "not 8am MT; no-op" and
   the on-hour one runs.

## Scope

This covers the **daily** pipeline. The monthly compilation/release flow
follows the same pattern and can be added as a second workflow once daily is
proven in production.
