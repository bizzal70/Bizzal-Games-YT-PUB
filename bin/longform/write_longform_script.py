#!/usr/bin/env python3
"""
write_longform_script.py — GPT-4o generates a full ~1,400 word structured
long-form YouTube script anchored to a topic brief and fixture data.

Reads:  BIZZAL_LONGFORM_ATOM_PATH (atom JSON)
        BIZZAL_LONGFORM_BRIEF (brief JSON)
Writes: back to atom file with script + script_id populated
"""
import sys, os, json, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../core"))

from datetime import datetime, UTC
from urllib import request

import system_config
from reference_paths import resolve_active_srd_path

REPO_ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SYSTEM_ID    = os.environ.get("BIZZAL_SYSTEM_ID", "").strip()
OPENAI_KEY   = os.environ.get("BIZZAL_OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("BIZZAL_OPENAI_MODEL", "gpt-4o")
REF_CFG      = os.path.join(REPO_ROOT, "config", "reference_sources.yaml")

SYSTEM_LABELS = {
    "dnd5e":      "D&D 5e (2024 rules)",
    "shadowdark": "Shadowdark RPG",
    "dcc":        "Dungeon Crawl Classics RPG",
}


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_fixture_sample(system_id: str, fixture_hint: str) -> list[dict]:
    """Load up to 10 entries from the relevant fixture file for context."""
    srd_path, _ = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    if not srd_path:
        return []
    type_map = {
        "spell":    "Spell.json",
        "creature": "Creature.json",
        "item":     "Item.json",
        "rule":     "Rule.json",
        "class":    "CharacterClass.json",
    }
    fname = type_map.get((fixture_hint or "").lower(), "Rule.json")
    fpath = os.path.join(REPO_ROOT, srd_path, fname)
    if not os.path.exists(fpath):
        return []
    try:
        data = load_json(fpath)
        if isinstance(data, list):
            return data[:10]
    except Exception:
        pass
    return []


def build_prompt(brief: dict, fixture_sample: list[dict], system_id: str) -> str:
    system_label = SYSTEM_LABELS.get(system_id, system_id)
    fixture_str = json.dumps(fixture_sample, indent=2, ensure_ascii=False)[:3000] if fixture_sample else "(no fixture data)"

    return f"""You are a script writer for Bizzal Games, a tabletop RPG YouTube channel.
System: {system_label}
Video title: {brief.get('title')}
Angle: {brief.get('angle')}
Rationale (why timely): {brief.get('rationale')}
Fixture type: {brief.get('fixture_hint')}

Sample fixture data for context:
{fixture_str}

Write a complete YouTube video script for an 8-10 minute video. Follow these rules:
- RTFM tone: fact-based, wry, no theatrical openers, no "picture this" or character framing
- Every sentence must contain a specific mechanic, number, condition, or ruling
- Structure: intro (30s) → 4-6 body sections (90-120s each) → outro (30s)
- Each body section has a clear heading and covers one distinct mechanic/ruling/application
- No filler, no padding, no generic advice
- Target ~1,400 words total

Return ONLY valid JSON with this exact schema (no markdown, no commentary):
{{
  "intro": "the intro script text (1 paragraph, ~75 words)",
  "sections": [
    {{
      "heading": "short heading for this section",
      "body": "full section script text (~200 words)"
    }}
  ],
  "outro": "the outro script text (~75 words, ends with a specific actionable CTA)",
  "word_count": <estimated total word count as integer>,
  "youtube_title": "optimised YouTube title (max 70 chars, no hashtags)",
  "youtube_description": "150-200 word YouTube description with timestamps placeholder and 5-8 hashtags at end"
}}"""


def call_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        raise SystemExit("[write_longform_script] ERROR: BIZZAL_OPENAI_API_KEY not set")
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 3000,
    }).encode("utf-8")
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
    )
    with request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def main():
    atom_path = os.environ.get("BIZZAL_LONGFORM_ATOM_PATH", "")
    brief_raw = os.environ.get("BIZZAL_LONGFORM_BRIEF", "")

    if not atom_path or not os.path.exists(atom_path):
        raise SystemExit(f"[write_longform_script] ERROR: BIZZAL_LONGFORM_ATOM_PATH not set or missing: {atom_path}")
    if not brief_raw:
        raise SystemExit("[write_longform_script] ERROR: BIZZAL_LONGFORM_BRIEF not set")

    brief = json.loads(brief_raw)
    atom  = load_json(atom_path)

    fixture_sample = load_fixture_sample(SYSTEM_ID, brief.get("fixture_hint", ""))
    print(f"[write_longform_script] fixture sample: {len(fixture_sample)} entries ({brief.get('fixture_hint')})")

    print(f"[write_longform_script] calling {OPENAI_MODEL}...")
    raw = call_openai(build_prompt(brief, fixture_sample, SYSTEM_ID))

    # Strip markdown fences if present
    clean = raw.strip()
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
    if clean.endswith("```"):
        clean = "\n".join(clean.split("\n")[:-1])

    try:
        script = json.loads(clean)
    except json.JSONDecodeError as e:
        raise SystemExit(f"[write_longform_script] ERROR: invalid JSON from GPT-4o: {e}\n{raw[:400]}")

    # Validate shape
    for k in ["intro", "sections", "outro"]:
        if k not in script or not script[k]:
            raise SystemExit(f"[write_longform_script] ERROR: script missing key: {k}")

    sections = script.get("sections", [])
    if not isinstance(sections, list) or len(sections) < 3:
        raise SystemExit(f"[write_longform_script] ERROR: need >= 3 sections, got {len(sections)}")

    # Compute script_id
    packed = f"{script['intro'].strip()}\n{json.dumps(sections)}\n{script['outro'].strip()}\n"
    script_id = sha256_text(packed)

    atom["script"]    = script
    atom["script_id"] = script_id
    atom["youtube_title"]       = script.get("youtube_title", atom.get("title", ""))
    atom["youtube_description"] = script.get("youtube_description", "")
    atom["word_count"]          = script.get("word_count", 0)
    atom["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    atomic_write_json(atom_path, atom)
    wc = script.get("word_count", "?")
    print(f"[write_longform_script] script written: {len(sections)} sections, ~{wc} words, script_id={script_id[:12]}")


if __name__ == "__main__":
    main()
