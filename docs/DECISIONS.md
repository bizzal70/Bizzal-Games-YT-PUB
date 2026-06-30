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

**Why**
- No longer maintaining a separate Umbrel server
- A single-machine setup makes the promotion/SSH ceremony unnecessary overhead
- Env-var-driven config is also a prerequisite for a future cloud-based v2 (see `docs/CLOUD_V2_PLAN.md` if present)
