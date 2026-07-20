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
import script_quality
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


def _db_system_label(system_id: str) -> str:
    """Display name for a system not in the static map (e.g. a newly added one),
    read from the rpg_systems DB. Falls back to the raw id."""
    try:
        return system_config.get_system(system_id).get("display_name") or system_id
    except Exception:
        return system_id

# Channel identity for the end card + description links. The end card text is
# ALSO narrated (renderer shares one string per segment), so keep it natural
# language -- the raw @handles / URLs live in the description where they're
# clickable and don't get read aloud awkwardly.
YT_CHANNEL_HANDLE = "@Bizzal_Games"
YT_CHANNEL_URL    = "https://www.youtube.com/@Bizzal_Games"
IG_HANDLE         = "@bizzalgames70"
IG_URL            = "https://www.instagram.com/bizzalgames70"
# Sibling TTRPG project — topically aligned, so cross-promo belongs on gaming
# videos (crypto/cyber blogs deliberately do NOT go here).
WRITTEN_BLOG_URL  = "https://bizzal70.github.io/itsalreadywritten/"
WRITTEN_X_HANDLE  = "@ItsAlrdyWritten"


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
    system_label = SYSTEM_LABELS.get(system_id) or _db_system_label(system_id)
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
- TITLE RULE: the youtube_title must copy the channel's proven Shorts formula — a
  specific named subject + a concrete, often counterintuitive ruling or
  consequence. Declarative and factual. NO colon-hype, NO vague gerund hooks
  ("Unpacking", "Unlocking"), NO marketing words ("Chaos", "Vintage", "Ultimate",
  "Secrets"). Anchor it to the single most surprising specific mechanic in THIS
  video. Good examples: "Barrier Tattoo only works without armor" /
  "Spell Casting Check consumes the slot on failure" /
  "Halflings have the best Luck economy in the game". Bad (do NOT do this):
  "Clownish Evolution: Unpacking Chaos in DCC" / "Gary's Appendix: Unlocking Vintage Spells".

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
  "youtube_title": "specific subject + concrete counterintuitive ruling, max 70 chars, no hashtags, no colon-hype (see TITLE RULE)",
  "youtube_description": "150-200 words. FIRST line = the single most specific, surprising ruling from the video, in the same dry factual voice as the title (no hype). Then 2-3 sentences on the concrete mechanics covered. Plain and specific, no marketing adjectives. End with 5-8 relevant hashtags."
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


def _generate_and_validate(brief: dict, fixture_sample: list, system_id: str) -> dict:
    """One generation attempt: call the model, parse it, validate the shape.
    Raises ValueError on anything malformed so the caller can retry."""
    raw = call_openai(build_prompt(brief, fixture_sample, system_id))
    clean = raw.strip()
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
    if clean.endswith("```"):
        clean = "\n".join(clean.split("\n")[:-1])
    try:
        script = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON from model: {e}")
    for k in ["intro", "sections", "outro"]:
        if k not in script or not script[k]:
            raise ValueError(f"script missing key: {k}")
    sections = script.get("sections", [])
    if not isinstance(sections, list) or len(sections) < 3:
        raise ValueError(f"need >= 3 sections, got {len(sections)}")
    return script


def _narration_text(script: dict) -> str:
    """The spoken body the editor judges: intro + each section + outro."""
    parts = [(script.get("intro") or "").strip()]
    for s in script.get("sections") or []:
        h = (s.get("heading") or "").strip()
        b = (s.get("body") or "").strip()
        parts.append(f"{h}. {b}" if h else b)
    parts.append((script.get("outro") or "").strip())
    return "\n\n".join(p for p in parts if p)


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

    # --- Generate + editorially judge, regenerating weak scripts ------------
    # The pipeline previously had only technical gates, so a mediocre script
    # still became a video. Now an editor scores each candidate against the
    # RTFM voice: below target we regenerate, below the floor we refuse to
    # publish at all. Fails OPEN (no key / API error => treated as passing).
    quality_attempts = int(os.environ.get("BIZZAL_SCRIPT_QUALITY_RETRIES", "2")) + 1
    system_label = SYSTEM_LABELS.get(SYSTEM_ID) or _db_system_label(SYSTEM_ID)
    best_script, best_verdict = None, None

    for attempt in range(1, quality_attempts + 1):
        print(f"[write_longform_script] calling {OPENAI_MODEL} (attempt {attempt}/{quality_attempts})...")
        try:
            candidate = _generate_and_validate(brief, fixture_sample, SYSTEM_ID)
        except Exception as exc:
            print(f"[write_longform_script] attempt {attempt} rejected: {exc}")
            continue

        verdict = script_quality.judge(
            _narration_text(candidate),
            context=f"{system_label} long-form: {brief.get('title')}",
        )
        if verdict.available:
            print(f"[write_longform_script] editor score={verdict.score:.1f} "
                  f"issues={verdict.issues or 'none'}")
        else:
            print("[write_longform_script] editor unavailable; accepting candidate")

        if best_verdict is None or verdict.score > best_verdict.score:
            best_script, best_verdict = candidate, verdict
        if verdict.ok:
            break
        if attempt < quality_attempts:
            print("[write_longform_script] below target; regenerating...")

    if best_script is None:
        raise SystemExit("[write_longform_script] ERROR: no valid script after all attempts")
    if not best_verdict.publishable:
        raise SystemExit(
            f"[write_longform_script] QUALITY GATE: best score {best_verdict.score:.1f} "
            f"below floor; refusing to publish. issues={best_verdict.issues}"
        )
    if not best_verdict.ok and best_verdict.available:
        print(f"[write_longform_script] WARN: publishing best-of at {best_verdict.score:.1f} "
              f"(below target) issues={best_verdict.issues}")

    script = best_script
    sections = script.get("sections", [])

    # Compute script_id
    packed = f"{script['intro'].strip()}\n{json.dumps(sections)}\n{script['outro'].strip()}\n"
    script_id = sha256_text(packed)

    # --- Render adapter -------------------------------------------------------
    # The shared renderer (bin/render/render_atom.sh) consumes script.hook/body/
    # cta: hook and cta are single title/end cards, and body is paginated into
    # narrated screens (each getting its own TTS + Replicate background art +
    # music). Long-form scripts are intro/sections/outro, so fold the full
    # narration into `body` (where it gets paginated and narrated screen by
    # screen), bracketed by a short title card and a subscribe end card. Without
    # this the renderer reads empty hook/body/cta and produces a silent, text-
    # less video — this is what makes long-form actually render its content.
    _blocks = []
    if (script.get("intro") or "").strip():
        _blocks.append(script["intro"].strip())
    for _s in sections:
        _h = (_s.get("heading") or "").strip()
        _b = (_s.get("body") or "").strip()
        if _b:
            _blocks.append(f"{_h}. {_b}" if _h else _b)
    if (script.get("outro") or "").strip():
        _blocks.append(script["outro"].strip())
    script["hook"] = (script.get("youtube_title") or atom.get("title") or "").strip()
    script["body"] = "\n\n".join(_blocks)
    # End card (also the spoken outro): natural language so TTS reads it well.
    script["cta"]  = (
        "Subscribe for weekly tabletop RPG deep dives. "
        "Follow Bizzal Games on YouTube and Instagram."
    )

    atom["script"]    = script
    atom["script_id"] = script_id
    atom["youtube_title"]       = script.get("youtube_title", atom.get("title", ""))
    # Description carries the clickable channel + IG links (the @handles live
    # here, not on the burned end card, so they aren't narrated awkwardly).
    _desc = (script.get("youtube_description", "") or "").rstrip()
    _links = (
        f"\n\nSubscribe on YouTube: {YT_CHANNEL_URL} ({YT_CHANNEL_HANDLE})"
        f"\nInstagram: {IG_URL} ({IG_HANDLE})"
        f"\n\nMore TTRPG rules & rulings — It's Already Written:"
        f"\n{WRITTEN_BLOG_URL} · {WRITTEN_X_HANDLE} on X"
    )
    atom["youtube_description"] = (_desc + _links).strip()
    atom["word_count"]          = script.get("word_count", 0)
    atom["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    atomic_write_json(atom_path, atom)
    wc = script.get("word_count", "?")
    print(f"[write_longform_script] script written: {len(sections)} sections, ~{wc} words, script_id={script_id[:12]}")


if __name__ == "__main__":
    main()
