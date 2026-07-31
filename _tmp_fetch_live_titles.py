import json, os

with open("_tmp_backfill_candidates.json", encoding="utf-8") as f:
    candidates = json.load(f)

ids = [c["vid"] for c in candidates]
print(f"IDS_COUNT:{len(ids)}")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
creds = Credentials.from_authorized_user_file(".secrets/youtube_token.json", SCOPES)
creds.refresh(Request())
yt = build("youtube", "v3", credentials=creds)

found = {}
for i in range(0, len(ids), 50):
    batch = ids[i:i + 50]
    resp = yt.videos().list(part="snippet,status", id=",".join(batch)).execute()
    for it in resp.get("items", []):
        found[it["id"]] = {
            "title": it["snippet"]["title"],
            "privacy": it["status"].get("privacyStatus", "?"),
        }

out = []
for c in candidates:
    v = c["vid"]
    if v in found:
        out.append({"vid": v, "live_title": found[v]["title"], "privacy": found[v]["privacy"]})
    else:
        out.append({"vid": v, "live_title": None, "privacy": "MISSING"})

with open("_tmp_live_titles.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"wrote {len(out)} live title records")
