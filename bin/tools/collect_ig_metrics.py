#!/usr/bin/env python3
"""Collect Instagram Reel/post insights and publish data/metrics/instagram.json.

Runs inside Bizzal-Games-YT-PUB, where the IG token already lives and already
posts every day — so the metrics repo (Audit_User_Agent) never needs a copy of
the IG secrets. Reads BIZZAL_IG_ACCESS_TOKEN + BIZZAL_IG_USER_ID from env,
mirroring bin/upload/upload_instagram.py. Never hard-fails.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

_BASE = "https://graph.instagram.com/v20.0"
_OUT = Path(__file__).resolve().parents[2] / "data" / "metrics" / "instagram.json"


def _get(path: str, params: dict) -> dict | None:
    url = f"{_BASE}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"[ig-metrics] {path} failed: {e}")
        return None


def collect(limit: int = 12) -> list[dict] | None:
    token = os.environ.get("BIZZAL_IG_ACCESS_TOKEN")
    uid = os.environ.get("BIZZAL_IG_USER_ID")
    if not token or not uid:
        print("[ig-metrics] missing BIZZAL_IG_* env")
        return None
    media = _get(
        f"{uid}/media",
        {"fields": "id,caption,media_type,permalink,timestamp", "limit": limit,
         "access_token": token},
    )
    if not media or "data" not in media:
        return None
    posts = []
    for m in media["data"]:
        mid = m.get("id")
        is_video = m.get("media_type") == "VIDEO"
        metric = (
            "reach,likes,comments,saved,shares,views"
            if is_video
            else "reach,likes,comments,saved"
        )
        ins = _get(f"{mid}/insights", {"metric": metric, "access_token": token}) or {}
        vals = {
            d.get("name"): (d.get("values", [{}]) or [{}])[0].get("value")
            for d in ins.get("data", [])
        }
        posts.append(
            {
                "id": mid,
                "permalink": m.get("permalink", ""),
                "timestamp": (m.get("timestamp", "") or "")[:10],
                "caption": (m.get("caption", "") or "")[:80],
                "media_type": m.get("media_type", ""),
                "reach": vals.get("reach"),
                "likes": vals.get("likes"),
                "comments": vals.get("comments"),
                "saved": vals.get("saved"),
                "shares": vals.get("shares"),
                "views": vals.get("views"),
            }
        )
    return posts


def main() -> int:
    posts = collect()
    if not posts:
        print("[ig-metrics] no data collected; leaving file unchanged")
        return 0
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "posts": posts,
    }
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ig-metrics] wrote {len(posts)} posts to {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
