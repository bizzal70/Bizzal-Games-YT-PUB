# Shadowdark Production Chain

This project supports a parallel Shadowdark daily chain alongside D&D 5e, both driven by the generic system scripts described in [docs/RPG_SYSTEMS.md](RPG_SYSTEMS.md). `rpg_systems.id = 'shadowdark'` in the config DB.

## Key design

- D&D and Shadowdark run side-by-side with separate atom, render, and approval-state paths, derived from `path_suffix` (`''` for `dnd5e`, `'_shadowdark'` for `shadowdark`).
- Shared core scripts are reused via `bin/core/system_env.sh <system_id>`.
- Cron installer supports `single`, `dual`, and `alternating` chain modes, iterating over whichever `rpg_systems` rows are `is_active`.

## Data paths used by the Shadowdark chain

- Incoming atoms: `data/atoms_shadowdark/incoming`
- Validated atoms: `data/atoms_shadowdark/validated`
- Failed atoms: `data/atoms_shadowdark/failed`
- Renders by day: `data/renders_shadowdark/by_day`
- Latest render: `data/renders_shadowdark/latest/latest.mp4`
- Approval state: `data/archive/approvals/discord_publish_gate_shadowdark.json`
- Publish registry: `data/archive/publish/published_registry_shadowdark.json`

## Reference files

- Source PDFs: `reference/shadowdark/source_pdfs`
- Active JSON dataset: `reference/shadowdark/active`

## Bootstrap JSON fixtures from PDFs

Run this once after PDFs are placed in `reference/shadowdark/source_pdfs`:

```bash
source .venv/bin/activate
python3 -m pip install pypdf
bin/core/bootstrap_shadowdark_fixtures.sh
```

The bootstrap writes starter fixture files required by the runtime pipeline:

- `CharacterClass.json`
- `Spell.json`
- `Item.json`
- `Creature.json`
- `Rule.json`
- plus empty join files (`CreatureAction*`, `CreatureTrait`, `SpellCastingOption`)

Note: This is a starter bootstrap. Improve/replace generated fixture content as your
curated Shadowdark dataset matures.

## Install cron

```bash
source .venv/bin/activate

# Run all active systems daily (e.g. D&D + Shadowdark)
BIZZAL_AUTOMATION_CHAIN_MODE=dual \
  bin/core/install_cron_automation.sh
```

## Verify cron entries

```bash
crontab -l | sed -n '/BEGIN BIZZAL_AUTOMATION/,/END BIZZAL_AUTOMATION/p'
```

## Manual Shadowdark run

```bash
source .venv/bin/activate
bin/core/run_daily_diag_for_system.sh shadowdark
```

## Manual Shadowdark publish gate check

```bash
source .venv/bin/activate
bin/core/discord_publish_gate_for_system.sh shadowdark check --publish
```
