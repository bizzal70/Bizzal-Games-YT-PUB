# Promotion Runbook (Dev → GitHub → Umbrel)

## Goal
Stop production drift by making all code changes in dev first, validating there, then promoting to Umbrel via GitHub only.

## Non-Negotiable Rules
- Do not edit production code files directly on Umbrel except emergency containment.
- All normal fixes go: dev commit → GitHub → Umbrel pull.
- Keep secrets only in `/home/umbrel/.config/bizzal.env` (not committed).
- Keep `/home/umbrel/.config/bizzal.env` immutable (`chattr +i`) after updates.

## 1) Dev Change Workflow
Run in local dev repo (`/home/bizzal/Bizzal_Games_Pub`):

```bash
git checkout main
git pull --ff-only
# make changes locally
```

Validate syntax and core scripts:

```bash
bash -n bin/core/run_daily.sh
bash -n bin/core/run_daily_diag.sh
python3 -m py_compile bin/core/discord_publish_gate.py bin/upload/upload_youtube.py
```

Run a safe local smoke pass (no prod publish):

```bash
BIZZAL_DAILY_LOG_DIR=/tmp BIZZAL_REQUIRE_DISCORD_APPROVAL=1 bin/core/run_daily_diag.sh
```

Review expected behavior in logs:
- `run_daily.sh` prints upload deferred message.
- `run_daily_diag.sh` creates a Discord approval request.
- No direct `upload_youtube.py` invocation from `run_daily.sh`.

## 2) Promote to GitHub

```bash
git status -sb
git add -A
git commit -m "Describe the fix"
git push origin main
```

## 3) Deploy to Umbrel (Prod)
Run on Umbrel host in repo (`/home/umbrel/Bizzal_Games_Pub`):

```bash
git checkout main
git fetch origin
git pull --ff-only origin main
```

Verify clean working tree after pull:

```bash
git status -sb
```

Expected: no local code drift (no modified tracked files).

## 4) Production Config Guardrails
Keep env in `/home/umbrel/.config/bizzal.env` and lock it:

```bash
sudo chattr -i /home/umbrel/.config/bizzal.env
# edit file if needed
sudo chattr +i /home/umbrel/.config/bizzal.env
lsattr /home/umbrel/.config/bizzal.env
```

Minimum expected values:
- `BIZZAL_REQUIRE_DISCORD_APPROVAL=1`
- `BIZZAL_DISCORD_WEBHOOK_URL`
- `BIZZAL_DISCORD_BOT_TOKEN`
- `BIZZAL_DISCORD_CHANNEL_ID`
- `BIZZAL_DISCORD_APPROVER_USER_IDS`

Media feature values (if desired in output):
- `BIZZAL_ENABLE_TTS=1`
- `BIZZAL_ENABLE_BG_IMAGE=1`
- `BIZZAL_ENABLE_BG_MUSIC=1`
- `OPENAI_API_KEY`
- `REPLICATE_API_TOKEN`

## 5) Cron Source of Truth
Required jobs:
- Daily pipeline run.
- Daily approval request.
- 5-minute approval check/publish.

Verify jobs:

```bash
crontab -l | grep -n 'run_daily_diag_cron.sh\|discord_publish_gate.py request --day\|discord_publish_gate.py check --publish'
```

## 6) Post-Deploy Verification
Run these on Umbrel after every deploy:

```bash
cd /home/umbrel/Bizzal_Games_Pub
bash bin/core/preflight_prod_env.sh
bash -n bin/core/run_daily.sh
bash -n bin/core/run_daily_diag.sh
python3 -m py_compile bin/core/discord_publish_gate.py bin/upload/upload_youtube.py
```

## 7) Incident Protocol (If Prod Misbehaves)
1. Contain first (disable uploader executable if needed).
2. Capture logs (`daily_diag`, request log, gate log).
3. Fix in dev only.
4. Commit + push.
5. Pull to Umbrel.
6. Verify with Post-Deploy Verification checklist.

Emergency containment command:

```bash
chmod -x /home/umbrel/Bizzal_Games_Pub/bin/upload/upload_youtube.py
```

Re-enable only after fix is deployed from GitHub:

```bash
chmod +x /home/umbrel/Bizzal_Games_Pub/bin/upload/upload_youtube.py
```

## 8) Rollback
Rollback should use Git, not manual script edits:

```bash
cd /home/umbrel/Bizzal_Games_Pub
git fetch --all --tags
git log --oneline -n 20
git checkout <known-good-commit-or-tag>
```

Then run Post-Deploy Verification again.
