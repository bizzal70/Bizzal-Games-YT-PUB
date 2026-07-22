#!/usr/bin/env python3
"""
content_safety.py -- the single source of truth for "is this topic/script
allowed to become a Bizzal Games video?"

Two independent incidents shipped confabulated long-form videos + clips:
  * "Godzilla in D&D 5e" (2026-07-22)  -- third-party IP, homebrew statblock
  * "Shadowdark Summoner class" (2026-07-20) -- Summoner is a DAGGERHEART class;
    it does not exist in Shadowdark. Presented as established Shadowdark rules.

Root cause: the topic scout mapped ANY trending headline onto one of our three
systems, and the long-form generator will confidently invent rules for a subject
that has no grounding in the system. The quality judge (script_quality.py) makes
this WORSE, not better: it rewards confident specificity, so a well-written
fabrication scores high and sails through.

This module provides three layers, used at two choke points:
  1. brief_is_safe(brief)         -- scout front door (topic queue)
  2. scan_text(text)              -- deterministic IP / wrong-system scan of the
                                     FINAL script+title (no API, always on)
  3. canon_check(script, system)  -- LLM accuracy fact-check of the final script
                                     (catches invented in-system content that the
                                     denylist can't -- e.g. "Shadowdark Summoner")

Layers 2 and 3 are defense-in-depth behind the scout guard. Layer 2 is
deterministic and cheap; layer 3 needs an LLM and is the only thing that can tell
"Summoner is not a Shadowdark class" from "Arcana Unleashed is a real D&D book."
"""
import json
import os
import re
from dataclasses import dataclass, field
from urllib import request


# --------------------------------------------------------------------------- #
# Denylist -- non-owned properties that must never be a video SUBJECT.
# Matched word-boundaried across a brief's fields or a script's text.
# Deliberately conservative: dropping an ambiguous topic costs nothing (the
# curated facts DB is the real content backbone); publishing "Shadowdark's
# Dragonbane" or a "Godzilla" statblock costs brand trust / IP exposure.
# --------------------------------------------------------------------------- #
_BLOCKED_TERMS = {
    # non-TTRPG franchises / protected IP (never a legitimate video subject)
    "godzilla", "kaiju", "marvel", "avengers", "dc comics", "batman", "superman",
    "pokemon", "pokémon", "star wars", "star trek", "lord of the rings",
    "tolkien", "the witcher", "warhammer", "elden ring", "dark souls", "zelda",
    "mario", "minecraft", "fortnite", "harry potter", "disney",
    "game of thrones", "one piece", "naruto", "dragon ball", "sonic the",
    "halo", "call of duty",
    # other commercial TTRPGs we do NOT cover (confabulation risk if forced in)
    "pathfinder", "daggerheart", "dragonbane", "mausritter", "mothership",
    "call of cthulhu", "vampire the masquerade", "world of darkness",
    "cyberpunk", "blades in the dark", "mork borg", "mörk borg",
    "numenera", "savage worlds", "gurps", "fate core", "starfinder",
    "lancer", "traveller",
}

# high-precision crossover framing ("X Meets D&D") -- a net for IP the denylist
# has not enumerated. Kept narrow: broad verb patterns ("integrate X into your
# game") false-positive on legitimate in-system topics.
_CROSSOVER_RE = re.compile(r"\b(meets|crossover|cross[- ]over|mash[- ]?up|versus)\b", re.I)


def _term_hits(blob: str) -> list:
    """Every denylisted term / crossover phrase present in `blob` (lowercased)."""
    hits = []
    low = blob.lower()
    for term in _BLOCKED_TERMS:
        if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low):
            hits.append(term)
    m = _CROSSOVER_RE.search(low)
    if m:
        hits.append(f"crossover:{m.group(0)}")
    return hits


def brief_is_safe(brief: dict) -> tuple:
    """(ok, reason) for a topic-queue brief. Scout front-door guard."""
    blob = " ".join(str(brief.get(k, "")) for k in
                    ("title", "angle", "rationale", "search_keyword"))
    hits = _term_hits(blob)
    if hits:
        return False, f"blocked property/system: {hits[0]!r}"
    return True, ""


def scan_text(text: str) -> tuple:
    """(ok, hits) deterministic IP / wrong-system scan of a FINAL script+title.
    No API; always safe to run; fails CLOSED (a hit blocks)."""
    hits = _term_hits(text or "")
    return (not hits), hits


# --------------------------------------------------------------------------- #
# LLM accuracy fact-check. Catches invented IN-SYSTEM content the denylist can't
# see (a "Shadowdark Summoner" script never says "Daggerheart").
# --------------------------------------------------------------------------- #
MODEL = os.environ.get("BIZZAL_CANON_MODEL", os.environ.get("BIZZAL_OPENAI_MODEL", "gpt-4o"))


def gate_enabled() -> bool:
    return (os.environ.get("BIZZAL_CANON_GATE") or "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


@dataclass
class CanonVerdict:
    grounded: bool = True
    available: bool = True
    verdict: str = ""
    problems: list = field(default_factory=list)
    raw: str = ""


_CANON_PROMPT = """You are a meticulous rules-accuracy fact-checker for a tabletop RPG channel that covers ONLY these three games:
- D&D 5e (2014 and 2024 rules)
- Shadowdark RPG (by The Arcane Library)
- Dungeon Crawl Classics RPG (by Goodman Games)

The script below is published as teaching real {system_label} content. Fact-check it for THREE failure modes:
1. FABRICATION: a mechanic, class, subclass, spell, monster, or rule presented as established, official {system_label} content that does NOT actually exist in {system_label}.
2. WRONG SYSTEM: content that actually belongs to a DIFFERENT game presented as {system_label} (e.g. a Daggerheart "Summoner" class taught as a Shadowdark class).
3. THIRD-PARTY IP: a non-TTRPG franchise used as the subject (Godzilla, Marvel, Pokemon, Star Wars, etc.).

Allowed (grounded = true):
- Discussing real, recently announced OFFICIAL products/rules for {system_label}, even if you are unsure of every detail.
- Clearly-labeled homebrew or optional variants IF the script explicitly frames them as homebrew / a house rule / "at your table" (not as official established rules).

Not allowed (grounded = false): presenting invented or wrong-system content as real, established {system_label} rules; or any third-party IP subject.

Judge only what is written. When a core subject of the script is fabricated or wrong-system, grounded = false.

Return ONLY JSON, no markdown:
{{"grounded": true|false, "verdict": "one sentence", "problems": ["short specific problem", "..."]}}

SCRIPT:
{script}"""


def _call_openai(prompt: str, api_key: str, timeout: int = 60) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 400,
    }).encode("utf-8")
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def _parse_canon(raw: str) -> CanonVerdict:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = "\n".join(s.split("\n")[1:])
    if s.endswith("```"):
        s = "\n".join(s.split("\n")[:-1])
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b > a:
        s = s[a:b + 1]
    try:
        d = json.loads(s)
    except Exception:
        return CanonVerdict(available=False, raw=raw)
    g = d.get("grounded")
    if not isinstance(g, bool):
        return CanonVerdict(available=False, raw=raw)
    problems = [str(p) for p in (d.get("problems") or [])][:6]
    return CanonVerdict(grounded=g, available=True,
                        verdict=str(d.get("verdict", "")), problems=problems, raw=raw)


def canon_check(script_text: str, system_label: str, api_key: str = "") -> CanonVerdict:
    """LLM accuracy fact-check. available=False when the judge could not run
    (no key / API error / unparseable) -- the CALLER decides fail-open vs closed."""
    if not gate_enabled():
        return CanonVerdict(available=False)
    api_key = api_key or os.environ.get("BIZZAL_OPENAI_API_KEY", "")
    if not api_key or not (script_text or "").strip():
        return CanonVerdict(available=False)
    try:
        raw = _call_openai(
            _CANON_PROMPT.format(system_label=system_label or "the system",
                                 script=script_text[:12000]),
            api_key)
    except Exception:
        return CanonVerdict(available=False)
    return _parse_canon(raw)


if __name__ == "__main__":
    import sys
    txt = sys.stdin.read()
    label = " ".join(sys.argv[1:]) or "D&D 5e"
    ok, hits = scan_text(txt)
    print(json.dumps({"scan_ok": ok, "ip_hits": hits}, indent=2))
    v = canon_check(txt, label)
    print(json.dumps({"grounded": v.grounded, "available": v.available,
                      "verdict": v.verdict, "problems": v.problems}, indent=2))
