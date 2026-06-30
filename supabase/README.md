# supabase/

This project's Supabase GitHub integration is connected to this repo
(`bizzal70/Bizzal-Games-YT-PUB`, working directory `.`). "Deploy to
production" is currently OFF in the Supabase dashboard (Project Settings ->
Integrations -> GitHub Integration), but the migration history has been
reconciled so it's now safe to turn on whenever you want it.

## Status: baseline reconciled

The baseline migration `20260630000000_initial_rpg_systems_schema` has been
recorded as **applied** in `supabase_migrations.schema_migrations` (the same
thing `supabase migration repair --status applied 20260630000000` does --
done via the SQL Editor because this laptop can't reach the DB directly; see
the IPv6 note below). So Supabase's migration-sync will now *skip* this file
instead of re-running it, and turning on "Deploy to production" is safe.

It's left off by default only as a deliberate choice -- flip it on in the
dashboard (Project Settings -> Integrations -> GitHub) whenever you want
merges to `main` to auto-apply new migration files.

## Connecting to the DB from a dev machine

The direct host `db.<ref>.supabase.co` is **IPv6-only**. On a machine with
no IPv6 route it will time out -- use the IPv4 **Session pooler** connection
string (Dashboard -> Connect) or the dashboard SQL Editor instead.

## How schema changes ship today

1. Make the change by hand via the Supabase SQL Editor (or any Postgres
   client) against the live DB.
2. Add a new timestamped file under `supabase/migrations/` with the same
   SQL, so the repo stays the source of truth for *what* changed and *why*.
   Use `YYYYMMDDHHMMSS_description.sql` naming.
3. Commit it alongside the code change that depends on it.

## If you ever need to re-reconcile (reference)

The baseline is already marked applied. If you ever stand up a fresh copy of
the DB from `bin/core/db_schema.sql` by hand and need the integration to skip
the baseline again, mark it applied with the Supabase CLI:

```bash
supabase login
supabase link --project-ref nlywxefvpibkqfctgmty
supabase migration repair --status applied 20260630000000 --linked
```

(or the equivalent `insert ... into supabase_migrations.schema_migrations`
via the SQL Editor, which is what was used originally since the direct DB
host is IPv6-only and unreachable from the dev laptop).

## Data seeding

Table contents (the `dnd5e`/`shadowdark` rows) were backfilled with
`bin/core/migrate_config_to_db.py`, not a `supabase/seed.sql` file -- that
script is the reference for what a full RPG system's worth of config rows
looks like. See [docs/RPG_SYSTEMS.md](../docs/RPG_SYSTEMS.md).
