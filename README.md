# Bizzal-Games-YT-PUB

Automated "content press" for Bizzal Games: it generates daily RPG content, renders it as a vertical YouTube Short (optionally with AI narration, music, and background art), and publishes to YouTube after a human approves it in Discord.

Runs entirely on a single local machine — no separate server required.

## What it does

1. **Generate** — picks a high-signal RPG fact/topic for the day and writes it as a content "atom" (JSON).
2. **Render** — turns the atom into a vertical MP4 (ffmpeg), optionally with AI background art, music, and TTS narration.
3. **Approve** — posts the script to Discord and waits for a human to reply `approve YYYY-MM-DD`.
4. **Publish** — uploads the approved video to YouTube.
5. **Archive** — keeps daily/monthly records for compilation videos and re-publishing.

Currently supports D&D 5e and Shadowdark content, generated from separate config (see [docs/SHADOWDARK_PRODUCTION.md](docs/SHADOWDARK_PRODUCTION.md) for how a second RPG system is wired in).

## Quickstart

```bash
git clone https://github.com/bizzal70/Bizzal-Games-YT-PUB.git
cd Bizzal-Games-YT-PUB
python3 -m pip install -r requirements.txt
cp .env.example ~/.config/bizzal.env   # fill in your own values
bin/core/run_daily.sh
```

The daily runner creates and validates the day's content atom, renders it (if a render script is present), and stops short of publishing (if an upload script is present) until the Discord approval gate clears it.

Useful checks after a run:

```bash
git status -sb
ls -la data/atoms/validated/
```

## Configuration

All credentials and feature toggles live in a local env file, never committed. Copy [.env.example](.env.example) and fill it in — it covers Discord (approval gate), YouTube OAuth, and the optional AI features (OpenAI for script polish/narration, Replicate for background art/music). Render-tuning knobs beyond that have working defaults; see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full list.

## Repo vs runtime

This repo tracks source, templates, and the reference RPG corpus (`reference/open5e/`, `reference/srd/`). Everything the pipeline *generates* — atoms, renders, logs, approval state — is intentionally not committed (`data/`, `runtime/`, `logs/`, `tmp/`).

## Structure

- `bin/` — core/render/upload scripts
- `config/` — content templates and per-RPG-system configuration
- `docs/` — deployment, ops, and decision-log documentation
- `reference/` — the SRD/RPG-system reference corpus used for content generation

## Where to go next

- **Running it day to day / on-call:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — daily/monthly commands, the Discord publish gate, scheduling, and the AI feature flags.
- **Making a change:** [docs/PROMOTION_RUNBOOK.md](docs/PROMOTION_RUNBOOK.md) — pre-commit checklist, rollback, incident response.
- **Adding/inspecting an RPG system:** [docs/SHADOWDARK_PRODUCTION.md](docs/SHADOWDARK_PRODUCTION.md) — how the parallel Shadowdark chain is wired in alongside D&D.
- **Why things are the way they are:** [docs/DECISIONS.md](docs/DECISIONS.md) and [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).
