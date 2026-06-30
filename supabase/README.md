# supabase/

This project's Supabase GitHub integration is connected to this repo
(`bizzal70/Bizzal-Games-YT-PUB`, working directory `.`), but **"Deploy to
production" is intentionally left OFF** in the Supabase dashboard
(Project Settings -> Integrations -> GitHub Integration).

## Why auto-deploy is off

Supabase's migration-sync expects the project's applied-migrations history
to match `supabase/migrations/*.sql` exactly. The schema currently live in
the DB was applied by hand via the SQL Editor before this folder existed, so
there's no Supabase CLI on record of what's "already applied." Turning on
auto-deploy without first reconciling that would make Supabase try to
re-run `20260630000000_initial_rpg_systems_schema.sql` as a brand-new
migration against a DB that already has these tables.

The migration file itself is written idempotently (`IF NOT EXISTS`), so
this would likely just no-op rather than error -- but it's not been
confirmed against a real CLI flow, so auto-deploy stays off until it has.

## How schema changes ship today

1. Make the change by hand via the Supabase SQL Editor (or any Postgres
   client) against the live DB.
2. Add a new timestamped file under `supabase/migrations/` with the same
   SQL, so the repo stays the source of truth for *what* changed and *why*.
   Use `YYYYMMDDHHMMSS_description.sql` naming.
3. Commit it alongside the code change that depends on it.

## Turning on auto-deploy later (optional)

Once the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)
is installed locally:

```bash
supabase login
supabase link --project-ref nlywxefvpibkqfctgmty
supabase migration repair --status applied 20260630000000
```

That marks the baseline migration as already applied without re-running it.
After that, flipping "Deploy to production" on in the dashboard is safe --
future merges to `main` will auto-apply any new files added under
`supabase/migrations/`.

## Data seeding

Table contents (the `dnd5e`/`shadowdark` rows) were backfilled with
`bin/core/migrate_config_to_db.py`, not a `supabase/seed.sql` file -- that
script is the reference for what a full RPG system's worth of config rows
looks like. See [docs/RPG_SYSTEMS.md](../docs/RPG_SYSTEMS.md).
