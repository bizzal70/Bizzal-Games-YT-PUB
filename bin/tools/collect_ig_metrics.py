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
import urllib.error
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
    except urllib.error.HTTPError as e:
        print(f"[ig-metrics] {path} -> {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:  # noqa: BLE001
        print(f"[ig-metrics] {path} failed: {e}")
    return None


def collect(limit: int = 12) -> list[dict] | None:
    token = os.environ.get("BIZZAL_IG_ACCESS_TOKEN")
    if not token:
        print("[ig-metrics] missing BIZZAL_IG_ACCESS_TOKEN")
        return None
    # Instagram Login flavor (token starts IGA...): list the authed user's own
    # media via me/media (the token identifies the account; no user-id needed).
    media = _get(
        "me/media",
        {"fields": "id,caption,media_type,permalink,timestamp", "limit": limit,
         "access_token": token},
    )
    if not media or "data" not in media:
        return None
    posts = []
    for m in media["data"]:
        mid = m.get("id")
        is_video = m.get("media_type") == "VIDEO"
        vals: dict = {}
        if is_video:
            # ig_reels_avg_watch_time is the metric that actually explains a
            # reach-without-engagement pattern (retention/scroll-past vs. a
            # caption/CTA problem) -- reach/likes/comments/saved/shares/views
            # alone can't distinguish the two. Try it first, but the insights
            # endpoint rejects the WHOLE request if one metric is invalid for
            # this media/product type or API version, so fall back to the
            # known-working set rather than losing everything over one addition.
            ins = _get(
                f"{mid}/insights",
                {"metric": "reach,likes,comments,saved,shares,views,ig_reels_avg_watch_time",
                 "access_token": token},
            )
            if ins is None:
                ins = _get(
                    f"{mid}/insights",
                    {"metric": "reach,likes,comments,saved,shares,views", "access_token": token},
                ) or {}
        else:
            ins = _get(
                f"{mid}/insights",
                {"metric": "reach,likes,comments,saved", "access_token": token},
            ) or {}
        vals = {
            d.get("name"): (d.get("values", [{}]) or [{}])[0].get("value")
            for d in ins.get("data", [])
        }
        posts.append(
            {
                "id": mid,
                "permalink": m.get("permalink", ""),
                "timestamp": (m.get("timestamp", "") or "")[:10],
                # Full caption (IG's own max is 2200) — never truncate here, or
                # reviewers mistake our cap for a real mid-sentence cut-off.
                "caption": (m.get("caption", "") or "")[:2200],
                "media_type": m.get("media_type", ""),
                "reach": vals.get("reach"),
                "likes": vals.get("likes"),
                "comments": vals.get("comments"),
                "saved": vals.get("saved"),
                "shares": vals.get("shares"),
                "views": vals.get("views"),
                "avg_watch_time_sec": vals.get("ig_reels_avg_watch_time"),
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
