#!/usr/bin/env python3
import os, json, sys, urllib.request, urllib.parse

G  = "\033[32m"
R  = "\033[31m"
NC = "\033[0m"
results = []

def check(name, fn):
    try:
        msg = fn()
        print(f"{G}PASS{NC}  {name}: {msg}")
        results.append((name, True, msg))
    except Exception as e:
        print(f"{R}FAIL{NC}  {name}: {e}")
        results.append((name, False, str(e)))

# 1. Secret presence
for key in [
    "BIZZAL_YT_CLIENT_ID","BIZZAL_YT_CLIENT_SECRET","BIZZAL_YT_TOKEN_JSON",
    "BIZZAL_OPENAI_API_KEY","BIZZAL_REPLICATE_API_TOKEN",
    "BIZZAL_DB_URL","SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY",
    "BIZZAL_IG_ACCESS_TOKEN","BIZZAL_IG_USER_ID",
]:
    def _check(k=key):
        v = os.getenv(k, "")
        if not v:
            raise ValueError("empty / not set")
        return f"set ({len(v)} chars)"
    check(f"secret:{key}", _check)

# 2. YouTube token JSON valid + live refresh
def check_yt_refresh():
    tok = json.loads(os.environ["BIZZAL_YT_TOKEN_JSON"])
    missing = [k for k in ["refresh_token","client_id","client_secret","token_uri"] if not tok.get(k)]
    if missing:
        raise ValueError(f"token JSON missing: {missing}")
    data = urllib.parse.urlencode({
        "client_id":     tok["client_id"],
        "client_secret": tok["client_secret"],
        "refresh_token": tok["refresh_token"],
        "grant_type":    "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    if "access_token" not in resp:
        raise ValueError(f"refresh failed: {resp}")
    return f"refreshed OK (expires_in={resp.get('expires_in','?')}s)"
check("youtube:token_refresh", check_yt_refresh)

# 3. YouTube channel accessible
def check_yt_channel():
    tok = json.loads(os.environ["BIZZAL_YT_TOKEN_JSON"])
    data = urllib.parse.urlencode({
        "client_id": tok["client_id"], "client_secret": tok["client_secret"],
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=10
    ) as r:
        access_token = json.loads(r.read())["access_token"]
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    items = resp.get("items", [])
    if not items:
        raise ValueError("no channel found")
    return f"channel: '{items[0]['snippet']['title']}'"
check("youtube:channel_access", check_yt_channel)

# 4. OpenAI
def check_openai():
    key = os.environ["BIZZAL_OPENAI_API_KEY"]
    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    return f"{len(resp.get('data',[]))} models accessible"
check("openai:api_key", check_openai)

# 5. Replicate
def check_replicate():
    import http.client, ssl
    token = os.environ["BIZZAL_REPLICATE_API_TOKEN"]
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("api.replicate.com", context=ctx, timeout=10)
    conn.request("GET", "/v1/account", headers={"Authorization": f"Token {token}"})
    r = conn.getresponse()
    body = r.read().decode()
    if r.status != 200:
        raise ValueError(f"HTTP {r.status}: {body[:120]}")
    resp = json.loads(body)
    return f"account: {resp.get('username','?')}"
check("replicate:api_token", check_replicate)

# 6. Postgres / Supabase DB
def check_db():
    import psycopg
    with psycopg.connect(os.environ["BIZZAL_DB_URL"], connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            db, user = cur.fetchone()
    return f"db={db} user={user}"
check("supabase:postgres", check_db)

# 7. Supabase REST API
def check_supabase_rest():
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(
        f"{url}/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()
    return "REST endpoint reachable"
check("supabase:rest_api", check_supabase_rest)

# 8. Instagram
def check_ig():
    token = os.environ["BIZZAL_IG_ACCESS_TOKEN"]
    req = urllib.request.Request(
        "https://graph.instagram.com/v20.0/me?fields=id,username",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    if "error" in resp:
        raise ValueError(resp["error"].get("message", str(resp["error"])))
    return f"@{resp.get('username','?')}"
check("instagram:access_token", check_ig)

# Summary
print()
print("=" * 55)
passed = sum(1 for _,ok,_ in results if ok)
failed = sum(1 for _,ok,_ in results if not ok)
print(f"Results: {passed} passed, {failed} failed")
if failed:
    print("\nFailed checks:")
    for name, ok, msg in results:
        if not ok:
            print(f"  - {name}: {msg}")
    sys.exit(1)
