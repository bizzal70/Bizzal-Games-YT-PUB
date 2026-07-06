# Database Migrations

All Supabase config changes go here as numbered SQL files **before** being applied.
This gives us full git history, rollback capability, and an audit trail.

## Convention

```
db/migrations/NNNN_description.sql
```

- `NNNN` — zero-padded sequence number (0001, 0002, ...)
- `description` — snake_case summary of the change

## Files

| File | Description |
|---|---|
| `0001_baseline_schema.sql` | CREATE TABLE statements for all config tables |
| `0002_baseline_seed_data.sql` | Baseline snapshot of all live config data (2026-07-06) |

## How to apply a new migration

1. Write your SQL change in a new file: `db/migrations/NNNN_your_change.sql`
2. Commit it to GitHub first (this is your audit trail)
3. Apply it in the Supabase SQL editor, or run:
   ```bash
   psql $BIZZAL_DB_URL < db/migrations/NNNN_your_change.sql
   ```
4. Update `db/applied/log.json` with the migration number, date, and a note

## Rules

- **Never edit an applied migration** — write a new one instead
- **Always commit before applying** — the repo is the source of truth
- **One concern per migration** — don't bundle unrelated changes
- If a migration fails halfway, write a compensating migration to fix it

## applied/log.json

Tracks which migrations have been applied to production Supabase.
Update it manually after each successful apply.
