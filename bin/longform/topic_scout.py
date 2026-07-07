#!/usr/bin/env python3
"""
topic_scout.py — weekly topic brief generator for long-form YouTube content.

Sources:
  - EN World RSS (enworld.org)
  - RPGSite RSS (rpgsite.net)
  - YouTube Data API v3 search (TTRPG trending)

Outputs:
  data/longform/topic_queue.json  — list of topic briefs, newest first
  Each brief: {system, title, angle, rationale, fixture_hint, created_date, status}

Usage: python bin/longform/topic_scout.py [--day YYYY-MM-DD]
"""
import sys, os, json, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../core"))

from datetime import datetime, UTC
from urllib import request, error as url_error
import xml.etree.ElementTree as ET

import system_config

REPO_ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
QUEUE_PATH  = os.path.join(REPO_ROOT, "data", "longform", "topic_queue.json")
OPENAI_KEY  = os.environ.get("BIZZAL_OPENAI_API_KEY", "")
YT_API_KEY  = os.environ.get("BIZZAL_YT_DATA_API_KEY", "")   # optional
OPENAI_MODEL = os.environ.get("BIZZAL_OPENAI_MODEL", "gpt-4o")

SYSTEMS = ["dnd5e", "shadowdark", "dcc"]

RSS_FEEDS = [
    ("EN World",  "https://www.enworld.org/ewr-porta/index.rss"),
    ("RPGSite",   "https://rpgsite.net/feed.atom"),
    ("RPGBOT",    "https://rpgbot.net/blog/feed/"),
]

YT_SEARCH_QUERIES = [
    "D&D 5e tips 2026",
    "Shadowdark RPG",
    "Dungeon Crawl Classics RPG",
    "OSR tabletop RPG",
    "TTRPG rules explained",
]

SYSTEM_LABELS = {
    "dnd5e":     "D&D 5e (2024 rules)",
    "shadowdark": "Shadowdark RPG",
    "dcc":       "Dungeon Crawl Classics RPG",
}


def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_queue() -> list:
    if not os.path.exists(QUEUE_PATH):
        return []
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def fetch_url(url: str, timeout: int = 10) -> bytes | None:
    try:
        req = request.Request(url, headers={"User-Agent": "BizzalGamesBot/1.0 (topic scout)"})
        with request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        print(f"  [scout] WARN: fetch failed {url}: {e}", file=sys.stderr)
        return None


def parse_rss(raw: bytes, source_name: str) -> list[str]:
    """Return list of title strings from RSS/Atom feed."""
    titles = []
    try:
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # Atom feed
        for entry in root.findall(".//atom:entry", ns):
            t = entry.find("atom:title", ns)
            if t is not None and t.text:
                titles.append(t.text.strip())
        # RSS feed
        for item in root.findall(".//item"):
            t = item.find("title")
            if t is not None and t.text:
                titles.append(t.text.strip())
    except Exception as e:
        print(f"  [scout] WARN: parse failed {source_name}: {e}", file=sys.stderr)
    return titles[:20]


def fetch_yt_titles(queries: list[str], api_key: str) -> list[str]:
    """Search YouTube Data API v3 and return video titles."""
    if not api_key:
        print("  [scout] WARN: BIZZAL_YT_DATA_API_KEY not set; skipping YouTube search", file=sys.stderr)
        return []
    titles = []
    for q in queries:
        from urllib.parse import urlencode
        params = urlencode({
            "part": "snippet",
            "q": q,
            "type": "video",
            "maxResults": 5,
            "order": "viewCount",
            "key": api_key,
        })
        url = f"https://www.googleapis.com/youtube/v3/search?{params}"
        raw = fetch_url(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for item in data.get("items", []):
                t = item.get("snippet", {}).get("title", "")
                if t:
                    titles.append(t)
        except Exception as e:
            print(f"  [scout] WARN: YT parse error: {e}", file=sys.stderr)
    return titles[:25]


def build_gpt_prompt(headlines: list[str], existing_titles: list[str], day: str) -> str:
    existing_str = "\n".join(f"- {t}" for t in existing_titles[:20]) or "(none yet)"
    headline_str = "\n".join(f"- {h}" for h in headlines[:40])
    systems_str  = "\n".join(f"- {k}: {v}" for k, v in SYSTEM_LABELS.items())

    return f"""You are a content strategist for a tabletop RPG YouTube channel called Bizzal Games.
The channel runs three systems:
{systems_str}

Today is {day}. You have scraped the following headlines from TTRPG news sites and YouTube trending searches:
{headline_str}

Topics already in the queue (avoid duplicates):
{existing_str}

Generate exactly 9 long-form YouTube video topic briefs — 3 per system. Each brief should:
- Be anchored to what the TTRPG community is actually talking about right now based on the headlines
- Focus on a specific mechanic, monster, spell, class, item, or rule — NOT a generic overview
- Match the tone: fact-based, wry, RTFM (no theatrical openers, no character framing)
- Be 8-12 minutes of content when expanded
- Include a fixture_hint: the specific fixture type to anchor to (spell/creature/item/rule/class)

Return ONLY a JSON array of exactly 9 objects. No markdown, no commentary. Schema:
[
  {{
    "system": "dnd5e|shadowdark|dcc",
    "title": "short punchy video title",
    "angle": "what specific angle makes this interesting",
    "rationale": "1 sentence: why this is timely based on the headlines",
    "fixture_hint": "spell|creature|item|rule|class",
    "search_keyword": "the headline or trend that inspired this"
  }}
]"""


def call_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        raise SystemExit("[scout] ERROR: BIZZAL_OPENAI_API_KEY not set")
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000,
    }).encode("utf-8")
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
    )
    with request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="")
    args = ap.parse_args()
    day = args.day.strip() or datetime.now(UTC).strftime("%Y-%m-%d")

    print(f"[topic_scout] day={day}")

    # Collect headlines
    headlines = []
    for name, url in RSS_FEEDS:
        print(f"  [scout] fetching {name}...")
        raw = fetch_url(url)
        if raw:
            titles = parse_rss(raw, name)
            print(f"  [scout] {name}: {len(titles)} titles")
            headlines.extend(titles)

    yt_titles = fetch_yt_titles(YT_SEARCH_QUERIES, YT_API_KEY)
    print(f"  [scout] YouTube: {len(yt_titles)} titles")
    headlines.extend(yt_titles)

    print(f"  [scout] total signal: {len(headlines)} headlines")

    # Load existing queue to avoid duplicates
    queue = load_queue()
    existing_titles = [b.get("title", "") for b in queue]

    # GPT-4o topic brief generation
    print("  [scout] calling GPT-4o for topic briefs...")
    prompt = build_gpt_prompt(headlines, existing_titles, day)
    raw_response = call_openai(prompt)

    # Parse JSON from response
    try:
        # Strip any accidental markdown fences
        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:])
        if clean.endswith("```"):
            clean = "\n".join(clean.split("\n")[:-1])
        briefs = json.loads(clean)
    except json.JSONDecodeError as e:
        raise SystemExit(f"[scout] ERROR: GPT-4o returned invalid JSON: {e}\n{raw_response[:500]}")

    if not isinstance(briefs, list) or len(briefs) == 0:
        raise SystemExit(f"[scout] ERROR: expected list of briefs, got: {type(briefs)}")

    # Stamp and validate each brief
    stamped = []
    for b in briefs:
        if not isinstance(b, dict):
            continue
        system = b.get("system", "").strip()
        if system not in SYSTEMS:
            print(f"  [scout] WARN: unknown system '{system}' in brief, skipping")
            continue
        b["created_date"] = day
        b["status"] = "pending"
        b["brief_id"] = hashlib.sha256(
            f"{day}|{system}|{b.get('title','')}".encode()
        ).hexdigest()[:12]
        stamped.append(b)

    print(f"  [scout] {len(stamped)} briefs validated")

    # Prepend new briefs (newest first), deduplicate by title
    existing_title_set = {b.get("title", "").lower() for b in queue}
    new_briefs = [b for b in stamped if b.get("title", "").lower() not in existing_title_set]
    merged = new_briefs + queue

    atomic_write_json(QUEUE_PATH, merged)
    print(f"[topic_scout] queue saved: {len(merged)} total briefs ({len(new_briefs)} new)")
    print(f"[topic_scout] path: {QUEUE_PATH}")


if __name__ == "__main__":
    main()
