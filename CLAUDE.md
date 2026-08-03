# CLAUDE.md

## Project Overview
Fully automated RPG YouTube/Instagram content pipeline for two channels: **@Bizzal_Games** (YouTube) and **@bizzalgames70** (Instagram). Three content lines run from this repo:
- **Shorts** (daily): pick a real fact from the fixture corpus → AI script → TTS → art → render → publish YouTube + Instagram Reels.
- **Long-form** (Mon/Wed/Fri, 8-10 min): topic-scouted from RSS/YouTube trends, but content must be grounded in a real fixture entity — see Boundaries. Publishes `unlisted` by default (workflow_dispatch); scheduled runs also default `unlisted` per the `longform_daily.yml` input default.
- **Clips** (auto, same run as long-form): each published long-form is cut into 2-3 native Shorts ("clips") that funnel viewers back to the full video — `bin/longform/make_clips_from_longform.py` + `run_clips_for_system.sh`, own registry (`published_registry_clips_{system}.json`), gated by the `make_clips` workflow input (default `true`).

Systems covered: **dnd5e, shadowdark, dcc** (confirmed via `reference/systems/` — all three have full fixture sets). Everything runs in GitHub Actions — there is no local runtime.

## Tech Stack
- Python (pipeline scripts), Bash (workflow runners)
- GitHub Actions (Cloud V2) — cron + workflow_dispatch
- OpenAI (gpt-4o script generation) · Replicate (flux-schnell art, stable-audio-2.5 music) · TTS (voice is persona/tone-driven, not fixed — see Architecture Notes; speed `BIZZAL_TTS_SPEED` = 0.9 for Shorts, 0.92 for long-form)
- YouTube Data API v3 (upload + captions) · Instagram Graph API (`graph.instagram.com`) for Reels
- Postgres via `BIZZAL_DB_URL` (content ledger, persona/tone config — NOT the fact source) · Supabase (`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`) for render archive storage (bucket `renders`)

## Commands
There is no local dev loop for this repo — validate everything via `workflow_dispatch`, never by running scripts locally.
```bash
# Trigger a Shorts dry run (generate + render, skip uploads)
gh workflow run daily.yml -f systems=all -f dry_run=true

# Trigger Shorts for one system, real publish
gh workflow run daily.yml -f systems=dnd5e -f privacy=unlisted

# Trigger long-form manually (defaults to unlisted)
gh workflow run longform_daily.yml

# Trigger the weekly topic scout manually (scheduled Mon 03:00 UTC = Sun evening MT)
gh workflow run topic_scout.yml

# Run the reusable content audit
gh workflow run content_audit.yml -f scope=today

# Refresh the YouTube OAuth token (two-step; see Environment / Secrets gotcha below)
gh workflow run reauth_youtube.yml
gh workflow run reauth_youtube.yml -f auth_code=<code from Google>
```
Other workflows present but not covered above: `check_secrets.yml`, `check_titles.yml`, `alert_on_failure.yml`, `ig_metrics.yml`, `monthly.yml`, `dump_db_migrations.yml` — inspect each before relying on it, not verified in this pass.

## Code Style
- No comments unless explaining non-obvious WHY (e.g. a schema gotcha or a prior incident).
- Field lookups across systems must never assume a shared schema — dnd5e/shadowdark/dcc store the same concept under different field names (e.g. `challenge_rating_decimal` vs `hp`/`ac`/`lv`). Always check the real fixture, never guess a field name.
- Prefer `os.environ.get("FOO") or "default"` over `os.environ.get("FOO", "default")` for any config that a workflow might pass as an empty string.

## Testing
- No local test suite — this pipeline is validated by running it (dry_run or workflow_dispatch) and reading real output: rendered script text, registry JSON, actual YouTube/IG posts.
- Before trusting a code change: run dry_run, inspect `data/state/published_registry_*.json` output, confirm tone/content against the active persona/tone config (Architecture Notes) — don't just confirm "it compiled."
- Deterministic fixture-membership (does this subject exist in `reference/systems/*/active/*.json`?) is the trustworthy grounding check. LLM canon_check is advisory only and has known false-positive patterns (assumes 2014 rules, doesn't know zine/expansion content) — never auto-act on a canon flag alone.

## Repository Etiquette
- Prefer PRs for anything touching the live publish path (Shorts or long-form daily workflows, uploaders, YouTube/IG credentials).
- Conventional-ish commits are fine (`fix:`, `feat:`) but not strictly enforced historically — match recent commit messages.
- Never force-push.

## Architecture Notes
- `bin/core/write_script_from_fact.py` — Shorts AI script generation. Tone is **persona/tone-driven from DB config** (`rpg_systems.persona_default`, `system_personas`, `system_tones`), not a single fixed rule — code fallback default is `"friendly_vet"`, with a `"wry_vet"` persona ("dry, world-weary veteran DM... slightly sardonic, no hype") migrated in as a DB default for dnd5e/shadowdark (`bin/core/migrate_tone_to_wry_vet.py`). A "senior engineer in a code review, not a storyteller" directive is still present in the prompt-building code as of this check — check current DB persona config before assuming which tone is actually live for a given system.
- `bin/core/fill_picks.py` — fact selection + short-term/long-term dedup (avoids recently-used fact pk/name/subtype-prefix by reading validated atoms + `published_registry_*`). Does NOT import `content_ledger.py`.
- `bin/core/content_ledger.py` — separate cross-pipeline dedup ledger keyed on normalized ruling text (not raw script hash), authoritative store is Postgres (`BIZZAL_DB_URL`) with a committed JSON mirror (`data/state/content_ledger.json`). Only referenced from `bin/upload/upload_youtube.py` and `bin/upload/upload_instagram.py` (i.e., a publish-time check), not from `fill_picks.py`.
- `bin/core/attach_fact.py` — resolves a fact_pk to the real fixture entry (base + traits/actions); the grounding source for both Shorts and long-form.
- `bin/core/content_safety.py` — single source of truth for IP/other-system denylist scan (`scan_text`) + advisory LLM canon_check. `bin/longform/topic_scout.py` imports and delegates to it directly (`content_safety.brief_is_safe`) — no duplicate denylist as of this check.
- `bin/longform/` — `topic_scout.py` (weekly scout, Mon 03:00 UTC), `pick_longform_system.py` (system rotation for `system=all`), `make_longform_atom.py` (fixture selection + safety gating), `write_longform_script.py` (script writer), `make_clips_from_longform.py` + `run_clips_for_system.sh` (long-form → Shorts clips)
- `bin/upload/upload_youtube.py`, `bin/upload/upload_instagram.py` — publish steps; both also consult `content_ledger.py`
- `reference/systems/{dnd5e,shadowdark,dcc}/active/*.json` — the real rules corpus (`Spell`, `Creature`, `CreatureAction`, `CreatureActionAttack`, `CreatureTrait`, `Item`, `Rule`, `CharacterClass`, `SpellCastingOption`), confirmed present and structurally identical across all three systems; this is the only legitimate grounding source, never invent content outside it
- `data/state/published_registry_{system}.json` / `_instagram.json` / `_longform_{system}.json` / `_clips_{system}.json` — publish logs + dedup state, committed to repo
- `docs/CONTENT_INTEGRITY.md` — postmortem + defenses + runbook for the confabulation incidents referenced below

## Boundaries — What NOT To Do
- **Cloud-only, no exceptions.** Never read from or write to a local clone (`C:\Users\bizza\Bizzal-Games-YT-PUB` is stale/behind). All reads/writes go through `gh api` (contents or Git Data API) or `gh workflow run`. Never create a working clone inside this machine's project dirs.
- **Never invent rules content.** Long-form previously confabulated items/classes/mechanics when driven by news headlines with no grounding (the "Godzilla in D&D 5e" and "Shadowdark Summoner" incidents). All script content — Shorts and long-form — must trace to a real `fact_pk` in `reference/systems/*/active/*.json`. News/trends may only bias which KIND of topic gets picked, never supply the content itself.
- **The low-DC humor lane is permanently disabled** (`BIZZAL_ENABLE_LOW_DC_HUMOR` defaults False). Do not re-enable without rebuilding it schema-aware per-system first — the old version treated every creature as low-threat due to a dead field lookup.
- **Instagram Graph API is publish-only** — no caption-edit or delete endpoint exists. Do not attempt to build one; corrections there are manual, in-app.
- **`reauth_youtube.yml` as currently written only requests `youtube.upload` + `youtube.readonly` scopes — it does NOT request `youtube.force-ssl`.** Running this workflow to refresh the token will silently drop caption-upload capability (`upload_captions` requires force-ssl). If force-ssl is needed, the scope list in both Step 1 (auth URL) and Step 2 (token exchange) in `.github/workflows/reauth_youtube.yml` must be edited first — confirmed by reading the workflow, not inferred.
- **Files over ~1MB via `gh api contents --jq .content` silently return empty** (GitHub Contents API limit) — use `-H "Accept: application/vnd.github.raw"` or the Git blobs API instead, or audits will silently read zero records and produce false "ungrounded" flags.
- **Don't batch fixes into the live pipeline.** One change at a time: implement, verify against real output (dry_run + registry/log inspection), report, then move to the next. This bit us with duplicate bugs shipped in one session before.
- **Never trust `os.environ.get("FOO", "default")` for optional Actions vars/secrets** — unset ones arrive as `""`, not absent, and silently defeat the dict-default.

## Workflow Preferences
- For anything touching the live publish workflows (`daily.yml`, `longform_daily.yml`) or uploader credentials, propose the change and get confirmation before merging/triggering a real (non-dry-run, non-unlisted) run.
- Validate via `workflow_dispatch` with `dry_run=true` or `privacy=unlisted` before any public/scheduled run depends on new code.
- Front-load known gotchas on any multi-step external setup (OAuth reauth, new API credentials) as one checklist before the user starts — don't drip them out reactively.

## Environment / Secrets
- `BIZZAL_CLOUD_SYSTEMS` — which systems run; `daily.yml` default is `"all"` (all three active systems, per `workflow_dispatch` input default in the current workflow)
- `BIZZAL_OPENAI_MODEL` — set to `gpt-4o` in both `daily.yml` and `longform_daily.yml` (do not silently drop back to `gpt-4o-mini`, tone quality regresses)
- `BIZZAL_IG_ACCESS_TOKEN` (60-day long-lived, needs periodic refresh) / `BIZZAL_IG_USER_ID`
- `BIZZAL_YT_CLIENT_ID` / `BIZZAL_YT_CLIENT_SECRET` / `BIZZAL_YT_TOKEN_JSON` — YouTube OAuth credentials
- `BIZZAL_GITHUB_PAT` — used by `reauth_youtube.yml` to run `gh secret set` from inside the workflow (needed in addition to the default `GITHUB_TOKEN`)
- `BIZZAL_YT_DATA_API_KEY` — enables YouTube-trend signal in the long-form topic scout (optional, RSS works without it)
- `BIZZAL_DB_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` — content ledger / persona config (Postgres) and render archive storage (Supabase), respectively

**Current YouTube token refresh process (verified against `.github/workflows/reauth_youtube.yml` — this replaces any prior manual OAuth Playground process, which is no longer how this repo does it):**
1. `gh workflow run reauth_youtube.yml` with no inputs → check the run log for a printed Google auth URL.
2. Open that URL, sign in as `bizzalgames70@gmail.com`, approve, copy the code Google gives you.
3. `gh workflow run reauth_youtube.yml -f auth_code=<code>` → workflow exchanges the code and calls `gh secret set BIZZAL_YT_TOKEN_JSON` directly — no manual paste into the GitHub secrets UI for this one.
4. **Known gap (see Boundaries):** the requested/saved scopes are hardcoded to `youtube.upload` + `youtube.readonly` only — force-ssl is not included, so caption upload will stop working after a reauth unless the workflow is edited first.
- GOTCHA (still applies to any secret you edit manually via the UI, e.g. `BIZZAL_IG_ACCESS_TOKEN`): the GitHub secret "Update secret" page always shows blank — saving with an empty/incomplete box wipes the secret silently. Always paste the full value and confirm the box is non-empty before saving.
