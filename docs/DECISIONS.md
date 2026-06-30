# Architecture Decisions Log

## 2026-02-12 — Use in-repo Copilot workflow as primary dev assistant
**Decision**
Use VS Code Copilot workflow directly in the repo as primary implementation assistant.

**Why**
- Direct file visibility and command execution
- Less drift vs out-of-band chat
- Easier continuity through committed docs and scripts

---

## 2026-02-12 — Keep render stage at MVP polish during pipeline stabilization
**Decision**
Prioritize deterministic, legible output over advanced visual polish in current stage.

**Why**
- Prevents over-optimization before core automation is stable
- Keeps focus on reliability of voice, metadata, upload, and scheduling

---

## 2026-02-12 — Enforce clean promotion path
**Decision**
Use this deployment flow: local test in WSL -> push to GitHub -> pull/run on Umbrel.

**Why**
- Clear source of truth
- Predictable production updates
- Easier rollback with tags/commits

---

## 2026-02-12 — Keep durable memory in repo docs
**Decision**
Persist project context in docs files so new sessions can bootstrap quickly.

**Why**
- Cross-session model memory is not guaranteed
- Repo-based memory is explicit and versioned

---

## 2026-06-30 — Retire Umbrel; run single-machine, local-only

**Decision**
Supersedes the 2026-02-12 "Enforce clean promotion path" entry. Drop the Umbrel home-server hosting and the dev → GitHub → Umbrel promotion flow. The pipeline now runs entirely on one local machine; hardcoded Umbrel paths/IP were scrubbed from scripts and docs in favor of repo-relative paths and `BIZZAL_*` env vars.

---

## 2026-06-30 — Move per-RPG-system config from YAML files to a DB (Supabase Postgres)

**Decision**
Replace `config/topic_spine*.yaml`, `config/style_rules*.yaml`, `config/reference_sources*.yaml`, and the 13 paired `*_dnd.sh`/`*_shadowdark.sh` wrapper scripts with rows in a Postgres database (`rpg_systems` + child tables, see `bin/core/db_schema.sql` and `docs/RPG_SYSTEMS.md`). `bin/core/system_config.py` provides DB-backed loaders that return the same dict shape the old YAML loaders did, so the content-generation logic itself didn't need to change. Wrapper scripts collapsed into generic `*_for_system.sh <system_id>` scripts; the alternating-cron day-parity branch now rotates over whatever systems are `is_active` in the DB.

**Why**
- Adding a third RPG system used to mean hand-authoring a new YAML triple plus a new wrapper-script set plus editing the alternating-cron branch logic by hand
- A DB-backed schema is what a future form UI can write to directly, without touching code or files
- Sets up the planned cloud v2 migration (Supabase is the chosen DB for that)

**Why**
- No longer maintaining a separate Umbrel server
- A single-machine setup makes the promotion/SSH ceremony unnecessary overhead
- Env-var-driven config is also a prerequisite for a future cloud-based v2 (see `docs/CLOUD_V2_PLAN.md` if present)
