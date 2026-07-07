# Bizzal-Games-YT-PUB

Fully automated content press for **Bizzal Games**: generates daily RPG content, renders it as a vertical YouTube Short (with AI narration, music, and background art), and publishes to YouTube — no human required in the cloud path. Also generates long-form YouTube videos (8-10 min) three times per week from AI-curated trending topics.

Runs entirely on **GitHub Actions**. No server or laptop required.

---

## What it produces

| Format | Cadence | Systems |
|---|---|---|
| YouTube Shorts (~55 sec) | Daily | D&D 5e, Shadowdark, DCC |
| Long-form YouTube (8-10 min) | Mon / Wed / Fri | D&D 5e → Shadowdark → DCC (rotating) |

---

## How it works

### Shorts pipeline (daily)

1. **Topic scout** — picks a daily category and angle from the weekly spine (DB-driven per system)
2. **Fact pick** — selects a spell, creature, item, rule, or class from the SRD fixture files
3. **Script** — GPT-4o writes a 90-word RTFM-tone script (hook / body / CTA)
4. **Render** — ffmpeg assembles: AI TTS narration (OpenAI) + AI background art per screen (Replicate/Flux) + AI background music (Replicate/Stable Audio) → vertical MP4
5. **Publish** — uploads to YouTube; archives MP4 to Supabase Storage
6. **State** — publish registry and style history committed back to repo for dedup/variety

### Long-form pipeline (Mon/Wed/Fri)

1. **Topic scout** (Sunday night) — scrapes EN World, RPGSite, and RPGBOT RSS feeds + YouTube trending search → GPT-4o generates 9 topic briefs (3 per system), saved to `data/longform/topic_queue.json`
2. **Atom** — pops next brief for the day's system, GPT-4o writes a full ~1,400 word structured script (intro + 4-6 sections + outro)
3. **Render** — same ffmpeg/TTS/Flux/Stable Audio stack, longer per-screen dwell (20s vs 6s)
4. **Publish** — uploads to YouTube as a standard (non-Shorts) video

---

## Active RPG systems

| System | ID | Fixtures | Tones | Notes |
|---|---|---|---|---|
| D&D 5e (2024) | `dnd5e` | 439 spells, 397 creatures, 982 items, 86 classes | neutral / gritty / ominous | Core SRD + XGtE + Tasha's + MMotM |
| Shadowdark | `shadowdark` | spells, creatures, items, classes | wry / gritty / ominous | |
| Dungeon Crawl Classics | `dcc` | 33 spells, 40 creatures, 7 classes, 12 rules, 12 items | neutral / gritty / ominous | Full spell-check result ladders; Dice Chain, Luck, Mighty Deeds mechanics |

All system config (topic spine, category angles, tones, voices, personas) lives in **Supabase** (`rpg_systems`, `system_weekly_spine`, `system_categories`, `system_tones`, `system_voices`, `system_personas`). No hardcoded system lists anywhere in the pipeline.

---

## Repo structure

```
bin/
  core/           daily pipeline: make_atom, fill_picks, attach_fact, pick_style,
                  write_script_from_fact, system_config, run_daily_for_system, ...
  render/         ffmpeg assembly, TTS, bg image, bg music synthesis
  upload/         YouTube + Instagram upload
  longform/       long-form pipeline: topic_scout, make_longform_atom,
                  write_longform_script, run_longform_for_system
  tools/          one-off enrichment utilities

config/           atom schema, style rules
data/
  state/          publish registries + style histories (committed, version-controlled)
    published_registry_{system}.json          Shorts dedup guard
    style_history_{system}.json               Shorts tone/voice variety
    published_registry_longform_{system}.json Long-form dedup guard
    style_history_longform_{system}.json      Long-form variety
  longform/
    topic_queue.json                          Long-form topic brief queue

reference/
  systems/
    dnd5e/active/     Spell.json, Creature.json, Item.json, CharacterClass.json, Rule.json
    shadowdark/active/
    dcc/active/       (DCC-specific fixture files)

.github/workflows/
  daily.yml           Daily Shorts pipeline (all systems, 8am MT)
  longform_daily.yml  Long-form pipeline (Mon/Wed/Fri, 10am MT)
  topic_scout.yml     Weekly topic brief generator (Sunday 9pm MT)
  monthly.yml         Monthly compilation video
```

---

## GitHub Actions workflows

| Workflow | Schedule | Trigger |
|---|---|---|
| `daily.yml` | 8am MT daily | All 3 systems; `systems=` input to target one |
| `longform_daily.yml` | 10am MT Mon/Wed/Fri | Rotates dnd5e→shadowdark→dcc |
| `topic_scout.yml` | 9pm MT Sunday | Populates `topic_queue.json` for the week |
| `monthly.yml` | 1st of month | Compiles month's Shorts into a compilation |

All workflows support `workflow_dispatch` with `dry_run=true` to generate + render without uploading.

---

## Required GitHub secrets

| Secret | Used by |
|---|---|
| `BIZZAL_DB_URL` | All — Supabase Postgres connection |
| `SUPABASE_URL` | All — Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | All — Storage + DB access |
| `BIZZAL_OPENAI_API_KEY` | Script generation, long-form scout |
| `BIZZAL_REPLICATE_API_TOKEN` | Background art + music (Flux/Stable Audio) |
| `BIZZAL_YT_CLIENT_ID` | YouTube OAuth |
| `BIZZAL_YT_CLIENT_SECRET` | YouTube OAuth |
| `BIZZAL_YT_TOKEN_JSON` | YouTube refresh token (materialized at runtime) |
| `BIZZAL_IG_ACCESS_TOKEN` | Instagram Reels upload |
| `BIZZAL_IG_USER_ID` | Instagram Reels upload |
| `BIZZAL_YT_DATA_API_KEY` | Long-form topic scout YouTube search (optional) |

---

## Supabase Storage

Bucket: `renders` (private)
- Shorts archived as `renders/{system}/{date}.mp4`
- Long-form archived as `renders/longform_{system}/{date}.mp4`

The archive step is non-fatal — a storage failure never blocks publishing.

---

## Adding a new RPG system

1. Add fixture files to `reference/systems/{id}/active/` — `Spell.json`, `Creature.json`, `Item.json`, `CharacterClass.json`, `Rule.json`, plus empty join stubs (`CreatureTrait.json`, `CreatureAction.json`, `CreatureActionAttack.json`, `SpellCastingOption.json`)
2. Initialize state files in `data/state/`: `published_registry_{id}.json` (`[]`), `style_history_{id}.json` (`{}`), `publish_gate_{id}.json`
3. Seed Supabase: insert rows into `rpg_systems`, `system_weekly_spine`, `system_categories`, `system_category_angle_weights`, `system_tones`, `system_voices`, `system_personas`
4. Add `published_registry_{id}.json` to the same-day rerun guard in `daily.yml`

See `bin/core/db_schema.sql` for the full DB schema.

---

## Manual / dry-run commands

```bash
# Dry run one system (generate + render, skip upload)
gh workflow run daily.yml --repo bizzal70/Bizzal-Games-YT-PUB \
  -f systems=dcc -f dry_run=true

# Dry run long-form
gh workflow run longform_daily.yml --repo bizzal70/Bizzal-Games-YT-PUB \
  -f system=dcc -f dry_run=true

# Run topic scout manually
gh workflow run topic_scout.yml --repo bizzal70/Bizzal-Games-YT-PUB

# Check last run logs
gh run list --repo bizzal70/Bizzal-Games-YT-PUB --limit 5
gh run view <run-id> --repo bizzal70/Bizzal-Games-YT-PUB --log | grep -E "archive_render|make_atom|render|upload"
```

---

## Where to go next

- **Cloud setup:** [docs/CLOUD_V2.md](docs/CLOUD_V2.md)
- **Deployment / local run:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Change runbook:** [docs/PROMOTION_RUNBOOK.md](docs/PROMOTION_RUNBOOK.md)
- **RPG system schema:** [docs/RPG_SYSTEMS.md](docs/RPG_SYSTEMS.md)
- **Decisions log:** [docs/DECISIONS.md](docs/DECISIONS.md)
