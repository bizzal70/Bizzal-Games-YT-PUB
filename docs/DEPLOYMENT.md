# Deployment Guide (Umbrel)

## Production Target
- Host: 192.168.68.128
- Platform: Umbrel Home Server
- Source: GitHub (`main` branch)

## Standard Deploy Flow
1. Push tested changes from dev machine to GitHub.
2. SSH into Umbrel host.
3. Pull latest from `origin/main`.
4. Ensure dependencies are present.
5. Run daily pipeline.
6. Verify logs and outputs.

## Example Commands
Run from Umbrel shell in repo root:

```bash
git pull --rebase
python3 -m pip install --user pyyaml
export BIZZAL_ACTIVE_SRD_PATH=/home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD
bin/core/run_daily.sh
```

## Reference Corpus Alignment (Umbrel-local)
- The production SRD JSON corpus can remain local on Umbrel and outside Git.
- Pipeline scripts resolve sources in this order:
	1) `BIZZAL_ACTIVE_SRD_PATH` (or `BG_ACTIVE_SRD_PATH`)
	2) `config/reference_sources.yaml` `active_srd_path`
	3) repo fallback `reference/srd5.1`

If you want a local dev mirror from Umbrel:

```bash
rsync -av --delete \
	umbrel@192.168.68.128:/home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD/ \
	reference/srd5.1/
```

Then verify:

```bash
bin/core/inventory_active_srd.py
ls -la data/reference_inventory/
```

## Verification Checklist
```bash
git status -sb
ls -la data/atoms/validated/
```

If render/upload scripts are present and executable, `run_daily.sh` will invoke them automatically.

## Operational Notes
- Keep production changes pull-only from GitHub (avoid ad-hoc manual edits on server)
- Prefer tagged releases for rollback points
- Save service/cron details here once finalized

## Rollback (Simple)
If needed, reset to a known tag/commit:

```bash
git fetch --tags
git checkout <known-good-tag-or-commit>
```

Then run pipeline checks again before resuming schedule.
