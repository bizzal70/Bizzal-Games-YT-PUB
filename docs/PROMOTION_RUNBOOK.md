# Change & Release Checklist

This used to document a dev → GitHub → Umbrel promotion flow across two machines. Now that everything runs on one local machine, there's no separate "promote to prod" step — just commit and you're live. This doc keeps the useful pre-commit checks and rollback/incident steps from that old process.

## 1) Before Committing

Validate syntax and core scripts:

```bash
bash -n bin/core/run_daily.sh
bash -n bin/core/run_daily_diag.sh
python3 -m py_compile bin/core/discord_publish_gate.py bin/upload/upload_youtube.py
```

Run a safe local smoke pass (no real publish):

```bash
BIZZAL_DAILY_LOG_DIR=/tmp BIZZAL_REQUIRE_DISCORD_APPROVAL=1 bin/core/run_daily_diag.sh
```

Review expected behavior in logs:
- `run_daily.sh` prints upload deferred message.
- `run_daily_diag.sh` creates a Discord approval request.
- No direct `upload_youtube.py` invocation from `run_daily.sh`.

## 2) Commit and Push

```bash
git status -sb
git add -A
git commit -m "Describe the fix"
git push origin main
```

## 3) Config Guardrails

Secrets live in your local env file (see `.env.example` / `bin/core/setup_publish_env.sh`), not committed to git.

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

## 4) Scheduling Source of Truth

Required jobs:
- Daily pipeline run.
- Daily approval request.
- 5-minute approval check/publish.

On Linux/WSL, verify cron jobs:

```bash
crontab -l | grep -n 'run_daily_diag_cron.sh\|discord_publish_gate.py request --day\|discord_publish_gate.py check --publish'
```

On native Windows, check the equivalent Windows Task Scheduler entries instead (see `docs/DEPLOYMENT.md`).

## 5) Post-Change Verification

Run these after any change that touches the pipeline scripts:

```bash
bash bin/core/preflight_prod_env.sh
bash -n bin/core/run_daily.sh
bash -n bin/core/run_daily_diag.sh
python3 -m py_compile bin/core/discord_publish_gate.py bin/upload/upload_youtube.py
```

## 6) Incident Protocol (If Something Misbehaves)

1. Contain first (disable the uploader executable if needed).
2. Capture logs (`daily_diag`, request log, gate log).
3. Fix the code.
4. Commit + push.
5. Verify with the Post-Change Verification checklist above.

Emergency containment command (Linux/WSL/Git Bash):

```bash
chmod -x bin/upload/upload_youtube.py
```

Re-enable once the fix is in:

```bash
chmod +x bin/upload/upload_youtube.py
```

(On native Windows without Git Bash, just rename the file temporarily instead.)

## 7) Rollback

Rollback should use Git, not manual script edits:

```bash
git fetch --all --tags
git log --oneline -n 20
git checkout <known-good-commit-or-tag>
```

Then run Post-Change Verification again.
