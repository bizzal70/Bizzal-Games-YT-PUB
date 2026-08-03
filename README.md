# Bizzal Games — Automated Content Pipeline

Fully automated content press for **Bizzal Games**. Generates daily RPG content, renders it as a vertical YouTube Short (AI narration + AI background art + AI background music), and publishes to YouTube and Instagram — no human required.

Also produces long-form YouTube videos (8–10 min) three times a week from AI-curated trending topics.

Runs entirely on **GitHub Actions**. No server or local clone needed.

---

## What it produces

| Format | Cadence | Systems |
|---|---|---|
| YouTube Shorts (~55 sec) | Daily, 8am MT | D&D 5e, Shadowdark, DCC |
| Instagram Reels | Daily (after Shorts) | D&D 5e, Shadowdark, DCC |
| Long-form YouTube (8–10 min) | Mon / Wed / Fri, 10am MT | Rotates dnd5e → shadowdark → dcc |

---

## Active RPG systems

| System | ID | Content |
|---|---|---|
| D&D 5e (2024) | `dnd5e` | 439 spells · 397 creatures · 982 items · 86 classes |
| Shadowdark | `shadowdark` | Spells · creatures · items · classes |
| Dungeon Crawl Classics | `dcc` | 33 spells · 40 creatures · 7 classes · 12 rules · 12 items |

All system config (topic spine, category weights, tones, voices, personas) lives in **Supabase** — not hardcoded. Adding a system means seeding the DB and dropping fixture files.

---

## Shorts pipeline (daily)

```
Topic scout → Fact pick → Script (GPT-4o-mini) → Render (ffmpeg) → Publish (YouTube + Instagram)
```

1. **Topic scout** — picks a category and angle from the weekly spine (DB-driven per system)
2. **Fact pick** — selects a spell, creature, item, rule, or class from SRD fixture files
3. **Script** — `gpt-4o-mini` writes a ~90-word RTFM-tone hook / body / CTA (model set by `BIZZAL_OPENAI_MODEL`, default `gpt-4o-mini`; long-form defaults to `gpt-4o`)
4. **Render** — ffmpeg assembles:
   - AI TTS narration (OpenAI)
   - AI background art per screen (Replicate / Flux) — style controlled by `BIZZAL_BG_STYLE`
   - AI background music (Replicate / Stable Audio)
5. **Quality gates** — every background image candidate is inspected before it's accepted, and rejected ones are regenerated (up to `BIZZAL_BG_IMAGE_CANDIDATE_ATTEMPTS`, default 4):
   - **text reject** (OCR / tesseract) — Flux renders prompt words as literal text; any image with readable text is discarded
   - **structure reject** (vision QA) — flags severe anatomical defects (headless or faceless figures, extra limbs, fused/melted bodies). Only **severe** defects reject; hooded, silhouetted, and frame-cropped figures are deliberately *not* flagged, so the bw/OSR style is safe. Disable with `BIZZAL_BG_IMAGE_ANATOMY_CHECK=0`
   - both gates **fail open** — a missing key or QA outage logs a warning and accepts the image rather than blocking the render

   If Replicate components (image or music) fail outright, render exits code 20 and publish is skipped; the run retries next day rather than releasing degraded content
6. **Publish** — uploads to YouTube (**public by default**; override per run with the `privacy` input), posts to Instagram Reels, archives MP4 to Supabase Storage
7. **State** — publish registry and style history committed back to repo for dedup and variety. Instagram dedups on **`(day, system)`** — one reel per system per day, which survives a re-run regenerating the atom

### Background style

Controlled by `BIZZAL_BG_STYLE` in `daily.yml`:

| Value | Description |
|---|---|
| `bw_rtfm` | Stark black-and-white pen-and-ink, 1970s RPG rulebook aesthetic *(current)* |
| `color_cinematic` | Rich color, cinematic lighting |
| `random` | Rotates through all presets each run |

---

## Long-form pipeline (Mon / Wed / Fri)

```
Topic scout (Sunday) → Atom → Script → Render → Publish
```

1. **Topic scout** (Sunday 9pm MT) — scrapes EN World, RPGSite, RPGBOT RSS + YouTube trending → GPT-4o generates 9 topic briefs (3 per system) → saved to `data/longform/topic_queue.json`
2. **Atom** — pops next brief for the day's system
3. **Script** — GPT-4o writes a full ~1,400-word structured script (intro + 4–6 sections + outro)
4. **Render** — same ffmpeg / TTS / Flux / Stable Audio stack; longer per-screen dwell (20s vs 6s)
5. **Publish** — uploads to YouTube as a standard video (not Shorts)

---

## Repo structure

```
.github/workflows/
  daily.yml                 Daily Shorts (all systems, 8am MT)
  longform_daily.yml        Long-form (Mon/Wed/Fri, 10am MT)
  topic_scout.yml           Weekly brief generator (Sunday 9pm MT)
  monthly.yml               Monthly compilation video
  reauth_youtube.yml        Manual YouTube OAuth refresh

bin/
  core/                     Daily pipeline: make_atom, fill_picks, attach_fact,
                            pick_style, write_script_from_fact, run_daily_for_system, ...
  render/                   ffmpeg assembly, TTS, bg image + music synthesis
  upload/                   YouTube + Instagram upload scripts
  longform/                 Long-form: topic_scout, make_longform_atom,
                            write_longform_script, run_longform_for_system
  tools/                    Enrichment utilities + collect_ig_metrics (read-only
                            IG insights for the reviewer/metrics agent)

config/                     Atom schema, style rules

data/
  state/                    All publish registries + style histories (committed)
    published_registry_{system}.json
    published_registry_longform_{system}.json
    published_registry_instagram.json
    style_history_{system}.json
    style_history_longform_{system}.json
  longform/
    topic_queue.json         Long-form topic brief queue
  metrics/
    instagram.json           Published IG insights (reach/likes/saves), read by
                             Audit_User_Agent — the IG token lives here, not there

reference/
  systems/
    dnd5e/active/           Spell.json, Creature.json, Item.json, CharacterClass.json, Rule.json
    shadowdark/active/
    dcc/active/

docs/                       Architecture, deployment, and runbooks
```

---

## GitHub Actions workflows

| Workflow | Schedule | What it does |
|---|---|---|
| `daily.yml` | 8am MT daily | Shorts for all 3 systems; `systems=` to target one, `privacy=` to override public |
| `longform_daily.yml` | 10am MT Mon/Wed/Fri | Long-form for rotating system |
| `topic_scout.yml` | 9pm MT Sunday | Populates `topic_queue.json` for the week |
| `monthly.yml` | 1st of month | Compiles month's Shorts into a compilation |
| `ig_metrics.yml` | 11:30 UTC daily | Read-only Instagram insights → `data/metrics/instagram.json` (consumed by [Audit_User_Agent](https://github.com/bizzal70/Audit_User_Agent)) |
| `content_audit.yml` | Scheduled + manual | SRD fact-check audit of generated content |
| `alert_on_failure.yml` | On pipeline-run failure | Alerts when a scheduled pipeline run fails |
| `reauth_youtube.yml` | Manual | Refreshes `BIZZAL_YT_TOKEN_JSON` secret when OAuth expires |
| `check_secrets.yml` | Manual | Verifies required secrets are present |
| `dump_db_migrations.yml` | Manual | Exports Supabase migrations |

All workflows support `workflow_dispatch` with `dry_run=true` to generate + render without uploading.

---

## Required GitHub secrets

| Secret | Purpose |
|---|---|
| `BIZZAL_DB_URL` | Supabase Postgres connection |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Storage + DB access |
| `BIZZAL_OPENAI_API_KEY` | Script generation, long-form topic scout |
| `BIZZAL_REPLICATE_API_TOKEN` | Background art + music (Flux / Stable Audio) |
| `BIZZAL_YT_CLIENT_ID` | YouTube OAuth app client ID |
| `BIZZAL_YT_CLIENT_SECRET` | YouTube OAuth app client secret |
| `BIZZAL_YT_TOKEN_JSON` | YouTube OAuth refresh token (materialized at runtime) |
| `BIZZAL_IG_ACCESS_TOKEN` | Instagram Reels publishing |
| `BIZZAL_IG_USER_ID` | Instagram Reels publishing |
| `BIZZAL_YT_DATA_API_KEY` | YouTube Data API v3 for long-form topic scout *(optional)* |

YouTube tokens are long-lived (Google app is in Production mode). Re-run `reauth_youtube.yml` if a pipeline run fails with `rc=9`.

---

## Supabase Storage

Bucket: `renders` (private)

- Shorts: `renders/{system}/{date}.mp4`
- Long-form: `renders/longform_{system}/{date}.mp4`

Archive step is non-fatal — a storage failure never blocks publishing.

---

## Manual operations

```bash
# Dry run — generate + render, skip upload
gh workflow run daily.yml --repo bizzal70/Bizzal-Games-YT-PUB \
  -f systems=dcc -f dry_run=true

# Dry run long-form
gh workflow run longform_daily.yml --repo bizzal70/Bizzal-Games-YT-PUB \
  -f system=dcc -f dry_run=true

# Force a smoke test (bypasses same-day rerun guard)
gh workflow run daily.yml --repo bizzal70/Bizzal-Games-YT-PUB \
  -f smoke_test=true -f systems=all -f privacy=unlisted

# Run topic scout manually
gh workflow run topic_scout.yml --repo bizzal70/Bizzal-Games-YT-PUB

# Refresh YouTube OAuth token
gh workflow run reauth_youtube.yml --repo bizzal70/Bizzal-Games-YT-PUB

# Check recent runs
gh run list --repo bizzal70/Bizzal-Games-YT-PUB --limit 10

# Stream logs from latest run
gh run view --repo bizzal70/Bizzal-Games-YT-PUB \
  $(gh run list --repo bizzal70/Bizzal-Games-YT-PUB --limit 1 --json databaseId -q '.[0].databaseId') \
  --log | grep -E "QUALITY|make_atom|render|upload|archive"
```

---

## Adding a new RPG system

1. Add fixture files to `reference/systems/{id}/active/`:
   `Spell.json`, `Creature.json`, `Item.json`, `CharacterClass.json`, `Rule.json`
   plus empty join stubs (`CreatureTrait.json`, `CreatureAction.json`, etc.)
2. Init state files in `data/state/`:
   `published_registry_{id}.json` → `[]`
   `style_history_{id}.json` → `{}`
   *(no `publish_gate_{id}.json` — the Discord approval gate was removed; the
   existing `publish_gate_*.json` files are orphaned leftovers)*
3. Seed Supabase tables:
   `rpg_systems`, `system_weekly_spine`, `system_categories`,
   `system_category_angle_weights`, `system_tones`, `system_voices`, `system_personas`
4. Add `published_registry_{id}.json` to the same-day rerun guard in `daily.yml`

Full DB schema: [`bin/core/db_schema.sql`](bin/core/db_schema.sql)

---

## Further reading

| Doc | What's in it |
|---|---|
| [docs/CLOUD_V2.md](docs/CLOUD_V2.md) | Cloud architecture and setup |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | First-time deployment steps |
| [docs/RPG_SYSTEMS.md](docs/RPG_SYSTEMS.md) | System config and Supabase schema |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture decision log |
| [docs/PROMOTION_RUNBOOK.md](docs/PROMOTION_RUNBOOK.md) | Runbook for production changes |
| [docs/ADDING_CONTENT.md](docs/ADDING_CONTENT.md) | How to add spells, creatures, items |
