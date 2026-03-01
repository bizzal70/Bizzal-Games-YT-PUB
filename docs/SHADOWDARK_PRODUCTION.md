# Shadowdark Production Chain

This project now supports a parallel Shadowdark daily chain in the same repository.

## Key design

- D&D and Shadowdark run side-by-side with separate atom, render, and approval-state paths.
- Shared core scripts are reused through env overrides.
- Cron installer supports `single`, `dual`, and `alternating` chain modes.

## Shadowdark wrappers

- `bin/core/shadowdark_env.sh`
- `bin/core/run_daily_diag_shadowdark.sh`
- `bin/core/run_daily_diag_shadowdark_cron.sh`
- `bin/core/discord_publish_gate_shadowdark.sh`
- `bin/core/run_daily_diag_alternating_cron.sh`

## Config files

- `config/reference_sources_shadowdark.yaml`
- `config/topic_spine_shadowdark.yaml`
- `config/style_rules_shadowdark.yaml`

## Data paths used by Shadowdark chain

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

Run this once on dev or prod after PDFs are placed in `reference/shadowdark/source_pdfs`:

```bash
cd /home/umbrel/Bizzal_Games_Pub
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

## Install cron on prod

```bash
cd /home/umbrel/Bizzal_Games_Pub
source .venv/bin/activate

# Run both chains daily (D&D + Shadowdark)
BIZZAL_AUTOMATION_CHAIN_MODE=dual \
  bin/core/install_cron_automation.sh
```

## Verify cron entries

```bash
crontab -l | sed -n '/BEGIN BIZZAL_AUTOMATION/,/END BIZZAL_AUTOMATION/p'
```

## Manual shadowdark run

```bash
cd /home/umbrel/Bizzal_Games_Pub
source .venv/bin/activate
bin/core/run_daily_diag_shadowdark.sh
```

## Manual shadowdark publish gate check

```bash
cd /home/umbrel/Bizzal_Games_Pub
source .venv/bin/activate
bin/core/discord_publish_gate_shadowdark.sh check --publish
```
