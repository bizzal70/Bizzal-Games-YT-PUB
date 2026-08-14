#!/usr/bin/env python3
"""
write_longform_script.py -- expand a REAL, assembled SRD fact into an 8-10 minute
grounded long-form script.

REWRITTEN 2026-07-22. The old version wrote from a NEWS brief with no grounding
and invented rules (the Godzilla/Summoner confabulations). This version consumes
`atom["fact"]` -- the real fixture entity assembled by attach_fact.py (base record
plus creature traits/actions/attacks, or spell/class fields) -- and instructs the
model to explain ONLY what that data (and widely-known, accurate rules for the
system) supports. Nothing is invented; the subject is a real entity from your corpus.

Reads:  BIZZAL_LONGFORM_ATOM_PATH  (atom JSON with `fact` attached)
Writes: back to the atom with script + script_id + youtube_title/description.
"""
import sys, os, json, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../core"))

from datetime import datetime, UTC
from urllib import request

import system_config
import script_quality

REPO_ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SYSTEM_ID    = os.environ.get("BIZZAL_SYSTEM_ID", "").strip()
OPENAI_KEY   = os.environ.get("BIZZAL_OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("BIZZAL_OPENAI_MODEL", "gpt-4o")
# The prompt asks for "~1,400 words" but that's guidance, not an instruction
# with teeth -- nothing enforced it, so the model was free to undershoot (and
# did: confirmed published long-form videos were landing at ~5 minutes / ~700
# words, about half the target, since the only hard check was ">=3 sections,
# non-empty"). Floor set a bit under the ~1,400 target to leave the model room
# without accepting a rewrite that's barely longer than a Short's script.
MIN_WORDS    = int(os.environ.get("BIZZAL_LONGFORM_MIN_WORDS", "1200"))

SYSTEM_LABELS = {"dnd5e": "D&D 5e (2024 rules)", "shadowdark": "Shadowdark RPG",
                 "dcc": "Dungeon Crawl Classics RPG"}

YT_CHANNEL_HANDLE = "@Bizzal_Games"
YT_CHANNEL_URL    = "https://www.youtube.com/@Bizzal_Games"
IG_HANDLE         = "@bizzalgames70"
IG_URL            = "https://www.instagram.com/bizzalgames70"
WRITTEN_BLOG_URL  = "https://bizzal70.github.io/itsalreadywritten/"
WRITTEN_X_HANDLE  = "@ItsAlrdyWritten"

_SKIP_FIELDS = {"name", "document", "slug", "id", "pk", "index", "desc_html",
                "illustration", "initialHeaderLevel", "url", "key"}


def sha256_text(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _db_system_label(system_id):
    try:
        return system_config.get_system(system_id).get("display_name") or system_id
    except Exception:
        return system_id


def fact_source_block(fact: dict) -> str:
    """Serialize the assembled real fact into an authoritative source block the
    model must write FROM (and only from)."""
    f = fact.get("fields") or {}
    lines = [f"NAME: {fact.get('name')}",
             f"KIND: {fact.get('kind')}",
             f"SOURCE: {fact.get('document') or 'system SRD'}"]
    for k, v in f.items():
        if k in _SKIP_FIELDS or v in (None, "", [], {}):
            continue
        sv = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        lines.append(f"{k}: {sv}"[:500])
    for label, key in (("TRAITS", "traits"), ("ACTIONS", "actions"),
                       ("ATTACKS", "attacks"), ("CASTING OPTIONS", "casting_options")):
        arr = fact.get(key) or []
        if arr:
            lines.append(f"\n{label}:")
            for e in arr[:25]:
                nm = e.get("name") or ""
                desc = e.get("description") or e.get("desc") or e.get("text") or ""
                lines.append(f"- {nm}: {desc}"[:400])
    return "\n".join(lines)[:6500]


def build_prompt(fact: dict, system_id: str) -> str:
    label = SYSTEM_LABELS.get(system_id) or _db_system_label(system_id)
    return f"""You are a script writer for Bizzal Games, a tabletop RPG YouTube channel.
System: {label}

You are writing an 8-10 minute deep dive on ONE real subject from the {label}
rules. Below is the AUTHORITATIVE data for that subject, taken directly from the
game's own reference. This is your ONLY source of facts about the subject.

=== AUTHORITATIVE SUBJECT DATA ===
{fact_source_block(fact)}
=== END DATA ===

HARD RULES (a violation makes the video worthless):
- Ground EVERY specific claim about the subject in the data above. Do NOT invent
  stats, abilities, traits, actions, spells, items, or subclasses that are not in
  the data. If the data does not support a number or mechanic, do not state it.
- You MAY explain how the subject interacts with widely-known, genuinely official
  {label} rules (action economy, conditions, saving throws, advantage, etc.) --
  but only real rules you are confident are official. Never invent a rule.
- Never introduce a different game system or any third-party franchise.
- Teach: tactics, common misplays, edge cases, and how a GM/player actually uses
  this at the table. Go deeper on the real material rather than inventing
  specifics -- depth means MORE genuine coverage (more misplays, more edge
  cases, more concrete examples from the data), not a shorter script.

LENGTH -- THIS IS A HARD REQUIREMENT, NOT A SUGGESTION:
- Total narration (intro + all section bodies + outro) MUST be AT LEAST 1,200
  words. A script under 1,200 words will be programmatically rejected and you
  will be asked to write it again -- so do not undershoot "to be safe" or
  because you think the subject is covered; write the full length every time.
- Structure: intro (~75 words) -> 6-8 body sections (~180-220 words EACH,
  every section a distinct real aspect: a mechanic, a common misplay, an edge
  case, a tactical use, a comparison to a related option) -> outro (~100 words
  ending in a concrete CTA). 6-8 sections at ~200 words each is how you reach
  1,200+ words -- if you are unsure you have enough real material for 6
  sections, pull another genuine angle from the data (a different action, a
  different interaction, a different table scenario) rather than writing fewer
  or shorter sections.

STYLE:
- RTFM tone: fact-based, wry, no theatrical openers, no "picture this", no hype.
- youtube_title: the real subject name + one concrete, often counterintuitive
  ruling from the data. Declarative, <=70 chars, no colon-hype, no hashtags.
  Good: "Gold Dragon Wyrmling punishes autopilot with a 15-foot cone".

Return ONLY valid JSON (no markdown), this exact schema:
{{
  "intro": "intro text (~75 words)",
  "sections": [{{"heading": "short heading", "body": "section text (180-220 words)"}}],
  "outro": "outro text (~100 words, ends with a specific CTA)",
  "word_count": <int, must be your ACTUAL total word count, and must be >= 1200>,
  "youtube_title": "subject + concrete ruling, <=70 chars, no hashtags",
  "youtube_description": "150-200 words: first line the single most specific real ruling from the data (dry, no hype), then the concrete mechanics covered, end with 5-8 relevant hashtags"
}}"""


def call_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        raise SystemExit("[write_longform_script] ERROR: BIZZAL_OPENAI_API_KEY not set")
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 4000,
    }).encode("utf-8")
    req = request.Request("https://api.openai.com/v1/chat/completions", data=payload,
                          headers={"Authorization": f"Bearer {OPENAI_KEY}",
                                   "Content-Type": "application/json"})
    with request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def _generate_and_validate(fact, system_id) -> dict:
    raw = call_openai(build_prompt(fact, system_id))
    clean = raw.strip()
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
    if clean.endswith("```"):
        clean = "\n".join(clean.split("\n")[:-1])
    try:
        script = json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON from model: {e}")
    for k in ("intro", "sections", "outro"):
        if k not in script or not script[k]:
            raise ValueError(f"script missing key: {k}")
    if not isinstance(script.get("sections"), list) or len(script["sections"]) < 3:
        raise ValueError(f"need >= 3 sections, got {len(script.get('sections', []))}")
    wc = len(_narration_text(script).split())
    if wc < MIN_WORDS:
        raise ValueError(f"narration too short: {wc} words (need >= {MIN_WORDS})")
    return script


def _narration_text(script) -> str:
    parts = [(script.get("intro") or "").strip()]
    for s in script.get("sections") or []:
        h = (s.get("heading") or "").strip()
        b = (s.get("body") or "").strip()
        parts.append(f"{h}. {b}" if h else b)
    parts.append((script.get("outro") or "").strip())
    return "\n\n".join(p for p in parts if p)


def main():
    atom_path = os.environ.get("BIZZAL_LONGFORM_ATOM_PATH", "")
    if not atom_path or not os.path.exists(atom_path):
        raise SystemExit(f"[write_longform_script] ERROR: atom path missing: {atom_path}")

    atom = load_json(atom_path)
    fact = atom.get("fact") or {}
    if not fact.get("name"):
        raise SystemExit("[write_longform_script] ERROR: atom has no grounded fact")

    system_label = SYSTEM_LABELS.get(SYSTEM_ID) or _db_system_label(SYSTEM_ID)
    print(f"[write_longform_script] subject: {fact.get('name')!r} ({fact.get('kind')})")

    attempts = int(os.environ.get("BIZZAL_SCRIPT_QUALITY_RETRIES", "2")) + 1
    best_script, best_verdict = None, None
    for attempt in range(1, attempts + 1):
        print(f"[write_longform_script] {OPENAI_MODEL} attempt {attempt}/{attempts}...")
        try:
            candidate = _generate_and_validate(fact, SYSTEM_ID)
        except Exception as exc:
            print(f"[write_longform_script] attempt {attempt} rejected: {exc}")
            continue
        verdict = script_quality.judge(_narration_text(candidate),
                                       context=f"{system_label} long-form: {fact.get('name')}")
        if verdict.available:
            print(f"[write_longform_script] editor score={verdict.score:.1f} issues={verdict.issues or 'none'}")
        else:
            print("[write_longform_script] editor unavailable; accepting candidate")
        if best_verdict is None or verdict.score > best_verdict.score:
            best_script, best_verdict = candidate, verdict
        if verdict.ok:
            break
        if attempt < attempts:
            print("[write_longform_script] below target; regenerating...")

    if best_script is None:
        raise SystemExit("[write_longform_script] ERROR: no valid script after all attempts")
    if not best_verdict.publishable:
        raise SystemExit(f"[write_longform_script] QUALITY GATE: best {best_verdict.score:.1f} "
                         f"below floor; refusing. issues={best_verdict.issues}")
    if not best_verdict.ok and best_verdict.available:
        print(f"[write_longform_script] WARN: publishing best-of at {best_verdict.score:.1f} "
              f"issues={best_verdict.issues}")

    script = best_script
    sections = script.get("sections", [])
    packed = f"{script['intro'].strip()}\n{json.dumps(sections)}\n{script['outro'].strip()}\n"
    script_id = sha256_text(packed)

    # Render adapter: the shared renderer reads script.hook/body/cta. Fold the full
    # narration into body (paginated + narrated per screen), hook = title card,
    # cta = end card.
    blocks = []
    if (script.get("intro") or "").strip():
        blocks.append(script["intro"].strip())
    for s in sections:
        h = (s.get("heading") or "").strip()
        b = (s.get("body") or "").strip()
        if b:
            blocks.append(f"{h}. {b}" if h else b)
    if (script.get("outro") or "").strip():
        blocks.append(script["outro"].strip())
    script["hook"] = (script.get("youtube_title") or fact.get("name") or "").strip()
    script["body"] = "\n\n".join(blocks)
    script["cta"] = ("Subscribe for new tabletop RPG deep dives every Monday, "
                     "Wednesday, and Friday. Follow Bizzal Games on YouTube and Instagram.")

    atom["script"] = script
    atom["script_id"] = script_id
    atom["title"] = fact.get("name")
    atom["youtube_title"] = script.get("youtube_title", fact.get("name", ""))
    _desc = (script.get("youtube_description", "") or "").rstrip()
    _links = (f"\n\nSubscribe for new tabletop RPG deep dives -- every Monday, Wednesday, and Friday."
              f"\nSubscribe on YouTube: {YT_CHANNEL_URL} ({YT_CHANNEL_HANDLE})"
              f"\nInstagram: {IG_URL} ({IG_HANDLE})"
              f"\n\nMore TTRPG rules & rulings -- It's Already Written:"
              f"\n{WRITTEN_BLOG_URL} - {WRITTEN_X_HANDLE} on X")
    atom["youtube_description"] = (_desc + _links).strip()
    # Real count, not the model's self-reported one -- that's the same soft
    # target the model was undershooting before the MIN_WORDS floor existed.
    atom["word_count"] = len(_narration_text(script).split())
    atom["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    atomic_write_json(atom_path, atom)
    print(f"[write_longform_script] written: {len(sections)} sections, "
          f"~{script.get('word_count','?')} words, script_id={script_id[:12]}")


if __name__ == "__main__":
    main()
