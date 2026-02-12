# Project State

Last updated: 2026-02-12

## Mission
Build an automated daily content press for Bizzal Games:
- Generate deterministic RPG content atoms
- Validate schema
- Render short-form vertical video
- Optionally upload/schedule to YouTube

## Current Status
- Deterministic atom pipeline is in place
- Validation step is integrated
- Daily runner scaffold exists
- Render pipeline exists and currently being tuned for layout/readability
- Upload stage is optional/stubbed based on script presence

## Confirmed Environment
- Dev environment: WSL + VS Code
- Source control: GitHub repo linked and synced
- Production environment: Umbrel Home Server
- Umbrel host IP: 192.168.68.128

## Repo Notes
- Main runner: `bin/core/run_daily.sh`
- Runtime outputs/reference corpuses are intentionally not committed
- Docs tags created:
  - v0.1-docs
  - v0.1.1-docs
  - v0.1.2-docs

## Near-Term Priorities
1. Keep render stage clean/legible, not over-polished
2. Complete deterministic audio/voice binding
3. Add metadata generation artifacts
4. Add upload automation with dry-run mode
5. Harden production daily cron/service workflow

## Working Principles
- Prefer deterministic outputs over visual complexity early
- Stabilize end-to-end pipeline before advanced polish
- Use small, safe commits with clear messages
- Keep production/deploy behavior scriptable and repeatable
