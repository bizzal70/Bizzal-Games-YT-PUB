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
bin/core/run_daily.sh
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
