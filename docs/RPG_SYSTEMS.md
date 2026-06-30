# RPG Systems (DB-driven config)

As of Phase 2, the editorial config that used to live in `config/topic_spine*.yaml`, `config/style_rules*.yaml`, and `config/reference_sources*.yaml` — plus the 13 paired `*_dnd.sh`/`*_shadowdark.sh` wrapper scripts — lives in a Postgres database (Supabase) instead. Adding a new RPG system is a data change, not a code change.

## Why

The old pattern required hand-authoring a full set of YAML files and a full set of wrapper scripts per system, plus editing the alternating-cron day-parity branch by hand. That doesn't scale past two systems and isn't form-UI-friendly. The DB schema captures the same data; a future form UI can write to these tables directly.

## Schema

See [bin/core/db_schema.sql](../bin/core/db_schema.sql) for the full DDL. Summary:

- `rpg_systems` — one row per system (`id`, `display_name`, `chain_tag`, `path_suffix`, `is_active`, ruleset/defaults, reference paths, feature flags, AI prompt prefixes).
- `system_weekly_spine` — which content category runs on which day of week.
- `system_categories` — per-category persona/tones/voices/angles (the `category_rules` block).
- `system_category_angle_weights` — weighted angle pool per category, used for the daily topic pick.
- `system_tones` — tone -> voice pack / TTS voice id pool.
- `system_voices` / `system_voice_category_lines` — hook/CTA script lines per voice, with optional per-category overrides.
- `system_personas` — persona one-liners.

`bin/core/system_config.py` provides `load_topic_spine(system_id)`, `load_style_rules(system_id)`, and `load_reference_sources(system_id)`, each returning the same dict shape the old YAML loaders produced — the rest of the pipeline didn't need to change.

## Adding a new RPG system

1. Insert a row into `rpg_systems` with a unique `id` (e.g. `pf2e`), a `path_suffix` (e.g. `_pf2e` — use something that doesn't collide with existing data dirs), and your defaults/reference paths/feature flags.
2. Populate `system_weekly_spine`, `system_categories`, `system_category_angle_weights`, `system_tones`, `system_voices` (+ `system_voice_category_lines` if you want per-category hook/CTA variants), and `system_personas` for that system.
3. Set `is_active = true` once it's ready to run.
4. Drop your reference JSON corpus under `reference/<your_system>/` and point `active_srd_path`/`srd_pdf_path` at it.
5. Run it manually to sanity check: `bin/core/run_daily_diag_for_system.sh <system_id>`.
6. Re-run `bin/core/install_cron_automation.sh` (in `dual` or `alternating` mode) — it queries active systems from the DB, so your new system is picked up automatically, no script edits needed.

`bin/core/migrate_config_to_db.py` is a reference for what a full system's worth of rows looks like (it's how `dnd5e` and `shadowdark` were originally migrated in).

## Running a system manually

All the old per-system wrapper scripts are gone, replaced by generic scripts that take a `system_id` argument:

| Old (deleted) | New |
|---|---|
| `dnd_env.sh` / `shadowdark_env.sh` | `system_env.sh <system_id>` |
| `run_daily_diag_dnd.sh` / `run_daily_diag_shadowdark.sh` (+ `_cron.sh` variants) | `run_daily_diag_for_system.sh <system_id>` |
| `discord_publish_gate_dnd.sh` / `discord_publish_gate_shadowdark.sh` | `discord_publish_gate_for_system.sh <system_id> [args]` |
| `monthly_publish_gate_dnd.sh` / `monthly_publish_gate_shadowdark.sh` | `monthly_publish_gate_for_system.sh <system_id> [args]` |
| `monthly_release_dnd_cron.sh` / `monthly_release_shadowdark_cron.sh` | `monthly_release_for_system_cron.sh <system_id> [args]` |

`bin/core/run_daily_diag_alternating_cron.sh` now rotates through whatever `rpg_systems` rows are `is_active` (by day-of-year modulo count) instead of a hardcoded D&D/Shadowdark day-of-month-parity branch.

## Note on monthly archive paths

Monthly paths are keyed by the bare `system_id`, not `path_suffix` (this matches the pre-existing convention, where monthly paths were suffixed even for the otherwise-unsuffixed default system). Since the D&D system's `id` is `dnd5e` (not the old `dnd`), if you have existing local `data/archive/monthly/dnd/` content from before this migration, move it to `data/archive/monthly/dnd5e/` manually — that data is gitignored/local-only, so this migration couldn't do it for you.

## Connection

Set `BIZZAL_DB_URL` (see `.env.example`) to your Supabase Postgres connection string. The pipeline scripts connect directly via `psycopg`; no REST API key is needed (and the tables have Row Level Security enabled, so the public REST API can't read this data even if the project's anon key leaks).
