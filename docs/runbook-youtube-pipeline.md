# Bizzal Games YT Pipeline — Operations Runbook

## Architecture

All execution is cloud-only via GitHub Actions. Nothing runs locally.
No local clones. All commits via `gh api`. Runtime = `.github/workflows/daily.yml`.

---

## Secrets (GitHub → bizzal70/Bizzal-Games-YT-PUB → Settings → Secrets)

| Secret | Description |
|--------|-------------|
| `BIZZAL_YT_CLIENT_ID` | Web app OAuth client ID (Bizzal Games Playground in GCP Console) |
| `BIZZAL_YT_CLIENT_SECRET` | Web app OAuth client secret — retrieve from GCP Console → Credentials → Bizzal Games Playground → ⓘ |
| `BIZZAL_YT_TOKEN_JSON` | Stored OAuth token JSON — contains refresh_token, must use same client_id/secret as above |

**Why Web app client, not Desktop:**
Google permanently blocked the OOB redirect (`urn:ietf:wg:oauth:2.0:oob`) that Desktop clients use.
OAuth Playground requires a Web app client with `https://developers.google.com/oauthplayground` as redirect URI.
The refresh token is tied to whichever client issued it — client_id/secret in token JSON must match.

---

## Token JSON format

```json
{
  "token": "<access_token from OAuth Playground>",
  "refresh_token": "<refresh_token from OAuth Playground>",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "<BIZZAL_YT_CLIENT_ID value>",
  "client_secret": "<BIZZAL_YT_CLIENT_SECRET value>",
  "scopes": [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
  ],
  "universe_domain": "googleapis.com",
  "account": "",
  "expiry": "<ISO8601 timestamp ~1hr from now>"
}
```

---

## CRITICAL: Why tokens expire after 7 days

If the OAuth consent screen is in **Testing** mode, Google hard-expires all refresh tokens after 7 days.
This is the root cause of recurring pipeline breakage around the 7-day mark.

**One-time fix — publish the consent screen to Production:**

1. GCP Console (bizzalgames70@gmail.com) → APIs & Services → OAuth consent screen
2. Click **"Publish App"** → confirm
3. Google verification is NOT required when authorizing your own account
4. Once published, refresh tokens last until revoked or 6 months of inactivity

---

## How to reauth YouTube (when token expires)

**Symptoms:** `ERROR: BIZZAL_YT_TOKEN_JSON secret is empty` or `invalid_grant` in logs.

**Steps:**

1. Go to https://developers.google.com/oauthplayground
2. Click gear icon top-right → check **"Use your own OAuth credentials"**
3. Enter Client ID and Client Secret from GCP Console → Credentials → **Bizzal Games Playground** → ⓘ
   - If secret is masked, click **"+ Add secret"** to generate a new one
   - If you add a new secret, also update the `BIZZAL_YT_CLIENT_SECRET` GitHub secret
4. In the scope box paste:
   `https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly`
5. Click **Authorize APIs** → sign in as **bizzalgames70@gmail.com**
   - If it defaults to bizzal70@gmail.com, switch accounts first
6. Click through the unverified app warning → **"Go to Bizzal Games YT Pipeline (unsafe)"**
7. Click **Exchange authorization code for tokens**
8. Copy the `refresh_token` value
9. Build the token JSON (format above) and set the secret:

```bash
printf '%s' '{...token JSON...}' \
  | gh secret set BIZZAL_YT_TOKEN_JSON -R bizzal70/Bizzal-Games-YT-PUB --body -
```

---

## Execute bit stability

`gh api PUT` always writes files as mode `100644` (not executable). The workflow has an
**"Ensure scripts are executable"** step that `chmod +x`s all pipeline scripts before execution.
This self-heals any mode loss caused by API-based file updates.

---

## Common failure modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ERROR: BIZZAL_YT_TOKEN_JSON secret is empty` | Token secret empty or not set | Reauth (see above) |
| `invalid_grant` in upload logs | Refresh token expired (app in Testing mode) | Reauth + publish consent screen to Production |
| `bg image synth script missing` | Execute bit lost on synthesize_bg_image_replicate.py | Workflow chmod step handles this automatically now |
| `QUALITY GATE: Replicate components missing` | BG image or music generation failed | Check BIZZAL_REPLICATE_API_TOKEN; check Replicate credits |
| IG posts but no YT | YT token expired | Reauth |
| Workflow file parse error | YAML syntax error in daily.yml | Validate YAML before committing |

---

## GCP Console reference

- Account: bizzalgames70@gmail.com
- OAuth clients: APIs & Services → Credentials
  - **Bizzal Games Playground** (Web application) — use for reauth via OAuth Playground
  - **Bizzal Games YT Pipeline** (Desktop) — legacy, do not use (OOB flow permanently blocked)
- OAuth consent screen: must be **Published** (not Testing) for long-lived tokens
