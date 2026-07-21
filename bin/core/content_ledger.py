#!/usr/bin/env python3
"""
content_ledger.py -- ONE cross-pipeline ledger of everything ever published,
keyed on the normalized RULING rather than the generated text.

Why this exists: dedup used to hash the generated script and lived in a
per-pipeline JSON file. Two consequences, both of which shipped duplicates:
  1. The same ruling reworded hashed differently and sailed through
     ("Deathbringer's Dice Mechanics: Multiple Rolls, Best Result" vs
      "Deathbringer's dice allow multiple rolls, best result").
  2. Shorts / long-form / clips each kept their own registry and could not
     see each other, so a clip could restate its own parent video.

This module fixes both: a canonical token key (case/punctuation/word-order and
light plural insensitive) PLUS a near-duplicate similarity check, stored once
in Postgres so every pipeline consults the same source of truth.

Storage: Postgres (BIZZAL_DB_URL) is authoritative; a committed JSON mirror
(data/state/content_ledger.json) keeps dedup working if the DB is unreachable.

Env:
    BIZZAL_DB_URL                    postgres URI (authoritative store)
    BIZZAL_DEDUPE_SIMILARITY         Jaccard threshold, default 0.70
    BIZZAL_DEDUPE                    "0" disables (NOT recommended)
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone

SIMILARITY = float(os.environ.get("BIZZAL_DEDUPE_SIMILARITY", "0.70"))

_STOP = {
    "a", "an", "the", "of", "to", "with", "and", "or", "on", "in", "at", "for",
    "is", "are", "was", "were", "be", "been", "by", "from", "as", "into",
    "than", "then", "that", "this", "it", "its", "their", "you", "your",
    "can", "will", "does", "do", "not", "but", "when", "while", "each",
    "every", "per", "if", "how", "why", "what", "which", "s",
}


def enabled() -> bool:
    return (os.environ.get("BIZZAL_DEDUPE") or "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


def tokens(text: str) -> set:
    """Significant tokens: lowercased, depunctuated, stopword-free, lightly
    de-pluralized so 'rolls'/'roll' and 'summoners'/'summoner' agree.

    CRITICAL: hashtags are stripped FIRST. Legacy titles carry heavy boilerplate
    ("Warlock • Class Spotlight #dnd #ttrpg #shorts") and those 3 identical tag
    tokens swamped the one word that actually distinguishes the video — Warlock
    vs Seer scored 0.71 and looked like a duplicate. Stripping tags drops that
    to 0.50 (correctly distinct) while true repeats still match exactly.
    """
    src = re.sub(r"#\w+", " ", (text or "").lower())
    raw = re.sub(r"[^a-z0-9\s]", " ", src)
    out = set()
    for w in raw.split():
        if w in _STOP or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


_SYSTEM_TAGS = (
    ("shadowdark", {"shadowdark"}),
    ("dcc", {"dcc", "dungeoncrawlclassics"}),
    ("dnd5e", {"dnd", "dnd5e", "dnd5e2024", "dungeonsanddragons"}),
)


def system_of(text: str) -> str:
    """Infer the game system from legacy hashtags ('#dnd', '#shadowdark').

    tokens() strips hashtags (they were causing false duplicates), which also
    removed the ONE tag that legitimately separates content: a D&D Warlock and
    a Shadowdark Warlock are different videos. We recover it here so the check
    can scope by system instead of merging them.
    """
    tags = set(re.findall(r"#(\w+)", (text or "").lower()))
    for system_id, group in _SYSTEM_TAGS:
        if tags & group:
            return system_id
    return ""


def content_key(text: str, system_id: str = "") -> str:
    """Stable key for an exact-ruling match (order/case/punctuation agnostic),
    SCOPED BY SYSTEM.

    The system must be part of the key, not just a comparison filter: it is the
    table's primary key, so without it a D&D Warlock and a Shadowdark Warlock
    collide and only one row is ever stored — leaving the other system with
    nothing to match against and letting a true repeat through.
    """
    sid = (system_id or system_of(text) or "").strip().lower()
    payload = f"{sid}|" + " ".join(sorted(tokens(text)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------- DB
_DDL = """
CREATE TABLE IF NOT EXISTS published_content (
    content_key  TEXT PRIMARY KEY,
    token_text   TEXT NOT NULL,
    system_id    TEXT,
    kind         TEXT,
    title        TEXT,
    video_id     TEXT,
    day          TEXT,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _connect():
    import psycopg
    url = os.environ.get("BIZZAL_DB_URL")
    if not url:
        raise RuntimeError("BIZZAL_DB_URL not set")
    return psycopg.connect(url, connect_timeout=10)


def _db_rows():
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
            conn.commit()
            cur.execute(
                "SELECT content_key, token_text, title, video_id, kind, day, system_id "
                "FROM published_content ORDER BY published_at DESC LIMIT 2000"
            )
            return [
                {"content_key": r[0], "token_text": r[1], "title": r[2],
                 "video_id": r[3], "kind": r[4], "day": r[5], "system_id": r[6]}
                for r in cur.fetchall()
            ]


def _db_insert(row: dict) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
            cur.execute(
                "INSERT INTO published_content "
                "(content_key, token_text, system_id, kind, title, video_id, day) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (content_key) DO NOTHING",
                (row["content_key"], row["token_text"], row.get("system_id"),
                 row.get("kind"), row.get("title"), row.get("video_id"), row.get("day")),
            )
            conn.commit()


# ------------------------------------------------------------------- JSON mirror
def _json_path(repo_root: str) -> str:
    return os.path.join(repo_root, "data", "state", "content_ledger.json")


def _json_rows(repo_root: str) -> list:
    try:
        with open(_json_path(repo_root), "r", encoding="utf-8") as f:
            return json.load(f).get("items", [])
    except Exception:
        return []


def _json_insert(repo_root: str, row: dict) -> None:
    p = _json_path(repo_root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    items = _json_rows(repo_root)
    if any(i.get("content_key") == row["content_key"] for i in items):
        return
    items.append(row)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"items": items[-3000:]}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


# ----------------------------------------------------------------------- public
def _load(repo_root: str):
    """(rows, source). DB is authoritative; JSON mirror is the fallback."""
    try:
        return _db_rows(), "db"
    except Exception as exc:
        print(f"[ledger] DB unavailable ({exc}); using JSON mirror")
        return _json_rows(repo_root), "json"


def check(text: str, repo_root: str, system_id: str = ""):
    """Return (is_duplicate, reason, match_row_or_None).

    Scoped by game system: the same ruling for D&D and for Shadowdark are
    DIFFERENT videos, so they must not block each other. When either side's
    system is unknown we still compare (conservative — better a rare false
    block, which is logged and diagnosable, than a duplicate slipping out).
    """
    if not enabled() or not (text or "").strip():
        return False, "", None
    sid = (system_id or system_of(text) or "").strip().lower()
    key, toks = content_key(text, sid), tokens(text)
    rows, source = _load(repo_root)

    def _comparable(r):
        rsid = (r.get("system_id") or "").strip().lower()
        return not (sid and rsid and sid != rsid)

    for r in rows:
        if _comparable(r) and r.get("content_key") == key:
            return True, f"exact ruling already published ({source})", r
    for r in rows:
        if not _comparable(r):
            continue
        sim = similarity(toks, set((r.get("token_text") or "").split()))
        if sim >= SIMILARITY:
            return True, f"near-duplicate {sim:.0%} of an existing ruling ({source})", r
    return False, "", None


def record(text: str, repo_root: str, *, system_id="", kind="", title="",
           video_id="", day="") -> str:
    """Persist a published ruling to BOTH stores. Returns the content key."""
    # Derive the system from legacy hashtags when the caller doesn't know it,
    # so backfilled rows are scopeable instead of blocking every system.
    sid = (system_id or system_of(text) or "").strip().lower()
    key = content_key(text, sid)
    row = {
        "content_key": key,
        "token_text": " ".join(sorted(tokens(text))),
        "system_id": sid, "kind": kind, "title": title,
        "video_id": video_id, "day": day,
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        _db_insert(row)
    except Exception as exc:
        print(f"[ledger] DB write failed ({exc}); JSON mirror still recorded")
    try:
        _json_insert(repo_root, row)
    except Exception as exc:
        print(f"[ledger] JSON mirror write failed: {exc}")
    return key
