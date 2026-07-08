# YouTube Auth Stability Runbook

**Problem this solves:** the daily pipeline keeps failing at the publish step with
`rc=9` / `invalid_grant` — YouTube OAuth token "expired or revoked" — roughly
every week. Videos generate + render fine but never upload.

---

## Why it keeps happening (root cause)

The pipeline refreshes the token every day, yet it still dies every ~7 days. That
symptom points to one classic cause:

**The Google OAuth app is in "Testing" publishing status.** Google expires refresh
tokens for *Testing* apps after **7 days**, regardless of usage. Moving the app to
**"In production"** removes that expiry entirely. This is the fix that actually
makes it stable — everything else is recovery/monitoring.

> Not yet confirmed from inside the repo (requires looking at Google Cloud
> Console). The "every ~7 days" pattern makes this the overwhelmingly likely cause.

---

## PART A — Permanent fix (do once, phone is fine)

1. Open **console.cloud.google.com** → sign in with the account that owns the
   YouTube channel.
2. Top-left project picker → select the project the YouTube API credentials live in.
3. Left menu → **APIs & Services → OAuth consent screen**.
4. Check **Publishing status**. If it says **"Testing"**, tap **"Publish app"** →
   confirm **"Push to production"**.
   - Status should then read **"In production"**.
   - You do **not** need Google verification for your own private/unlisted
     uploads — ignore the verification warning; uploads keep working.

This stops the weekly death. The already-dead token still has to be replaced once
(Part B).

---

## PART B — Recover publishing now (needs a computer + browser, ~5 min)

Re-minting the token requires a browser sign-in, so this part needs a laptop.

```bash
cd <repo>
git pull
. .venv/bin/activate
bin/upload/upload_youtube.py --refresh-auth-only
```
- It prints a Google URL → open it, approve, paste the code back.
- That writes a fresh token to the local token file
  (e.g. `~/.config/bizzal/youtube_token.json`).

Push the new token into GitHub (this is what CI actually uses):
- Copy the **entire contents** of the new token file.
- GitHub → repo → **Settings → Secrets and variables → Actions →
  `BIZZAL_YT_TOKEN_JSON`** → **Update** → paste → save.
  *(This paste step can be done from a phone once you have the token text.)*

Re-publish the already-rendered backlog (videos are built, just not uploaded — so
nothing is lost):
```bash
bash bin/core/recover_youtube_auth_and_backlog.sh --days YYYY-MM-DD
```

---

## PART C — Make failures loud (proposed code changes)

Today an auth failure is **silent** — you only find out when you go looking. Three
safeguards, in priority order:

1. **Alert on auth failure** — post a Discord/email ping the moment a run fails
   with `rc=9`, so you know same-day. *(recommended)*
2. **Preflight auth probe in `daily.yml`** — fail fast with a clear
   `YOUTUBE_AUTH=INVALID_GRANT` instead of rendering 3 full videos first and dying
   at upload (saves ~10 min of wasted compute per failed run). *(recommended)*
3. **Weekly auto-refresh canary** — scheduled workflow that refreshes the token on
   a cadence and warns *before* it goes stale. *(optional once in production mode)*

---

## Quick reference

| Symptom | Meaning | Action |
|---|---|---|
| `publish_rc=9` / `invalid_grant` | token expired or revoked | Part B (re-mint), then Part A if not done |
| `publish_rc=6` | duplicate publish blocked | expected safety, no action |
| `pending` | no valid approval seen | n/a for cloud (autopublish) path |

Fast status check of the approval/publish state:
```bash
jq '.approvals | to_entries[] | {day:.key,status:.value.status,content_id:.value.content_id}' \
  data/archive/approvals/discord_publish_gate.json | tail -n 20
```

Related code:
- `bin/upload/upload_youtube.py` — upload + auth (`--refresh-auth-only`, `rc=9` on `invalid_grant`)
- `bin/core/discord_publish_gate.py` — autopublish path used by the cloud pipeline
- `bin/core/recover_youtube_auth_and_backlog.sh` — pull + preflight + retry backlog
- `.github/workflows/daily.yml` — daily cloud pipeline
- `docs/DEPLOYMENT.md` — publish runbook (see `rc=9` notes)
