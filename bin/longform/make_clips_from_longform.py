#!/usr/bin/env python3
"""
make_clips_from_longform.py -- turn one long-form video into 2-3 standalone
Shorts ("clips") that funnel viewers to the full video.

The long-form is the depth content; Shorts are the discovery engine. Each clip
takes the sharpest ruling from a long-form section, rewritten as a native Short
(hook + short burned body for sound-off scrollers + a "full breakdown" CTA), and
carries a link to the source video in its description.

Reads:  the validated long-form atom (script.sections + youtube_title)
        the source long-form YouTube video id (for the funnel link)
Writes: N clip atoms to data/atoms_clips_{system}/validated/{clip_day}.json,
        each renderable by the normal Shorts path (render_atom.sh + upload).

Env: BIZZAL_OPENAI_API_KEY, BIZZAL_OPENAI_MODEL (default gpt-4o),
     BIZZAL_CLIPS_PER_LONGFORM (default 3).
"""
import sys, os, json, hashlib
from datetime import datetime, UTC
from urllib import request

REPO_ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
OPENAI_KEY   = os.environ.get("BIZZAL_OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("BIZZAL_OPENAI_MODEL", "gpt-4o")
MAX_CLIPS    = int(os.environ.get("BIZZAL_CLIPS_PER_LONGFORM", "3"))

SYSTEM_LABELS = {
    "dnd5e": "D&D 5e", "shadowdark": "Shadowdark", "dcc": "DCC",
}


def system_label(system_id: str) -> str:
    """Display label for a system: static map first, then the rpg_systems DB (so
    a newly added system reads correctly), then a generic fallback."""
    if system_id in SYSTEM_LABELS:
        return SYSTEM_LABELS[system_id]
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../core"))
        import system_config
        return system_config.get_system(system_id).get("display_name") or "TTRPG"
    except Exception:
        return "TTRPG"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def build_prompt(title: str, sections: list[dict], system_label: str, n: int) -> str:
    sect_str = "\n\n".join(
        f"[{i}] {s.get('heading','').strip()}\n{s.get('body','').strip()}"
        for i, s in enumerate(sections)
    )
    return f"""You are cutting a long-form {system_label} tabletop RPG video into short vertical clips for YouTube Shorts / Reels.

Long-form title: {title}

Sections:
{sect_str}

Pick the {n} STRONGEST, most self-contained rulings — the ones that work alone as a 30-second short and make a scroller stop. For each, write a native Short:
- "hook": one line, the channel's Shorts formula = specific named subject + concrete, often counterintuitive ruling. Declarative, factual. NO hype words, NO colon-clickbait. Examples: "Barrier Tattoo only works without armor" / "Spellcasting Check failures trigger chaos in DCC".
- "body": the burned on-screen script, 30-45 words, punchy, every sentence a specific mechanic/number/condition. This is ALSO narrated, so it must read naturally aloud. No filler.
- "youtube_title": same as hook or a tight variant, max 70 chars, no hashtags.
- "youtube_description": 1-2 sentences on the ruling (dry, factual), then a blank line. Do NOT add hashtags or links (added later).

Return ONLY valid JSON, no markdown:
{{"clips": [{{"hook": "...", "body": "...", "youtube_title": "...", "youtube_description": "..."}}]}}"""


def call_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        raise SystemExit("[make_clips] ERROR: BIZZAL_OPENAI_API_KEY not set")
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 1600,
    }).encode("utf-8")
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def parse_clips(raw: str) -> list[dict]:
    s = raw.strip()
    if s.startswith("```"):
        s = "\n".join(s.split("\n")[1:])
    if s.endswith("```"):
        s = "\n".join(s.split("\n")[:-1])
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        s = s[start:end + 1]
    return (json.loads(s) or {}).get("clips") or []


def make_clip_atom(system_id, day, clip, idx, video_id):
    sys_label = system_label(system_id)
    clip_day = f"{day}-{system_id}-clip{idx}"
    hook = (clip.get("hook") or "").strip()
    body = (clip.get("body") or "").strip()
    yt_title = (clip.get("youtube_title") or hook)[:70]
    watch = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    desc = (clip.get("youtube_description") or "").rstrip()
    if watch:
        desc += f"\n\n▶ Full breakdown ({sys_label}): {watch}"
    cta = "Full breakdown on the channel — link below."
    script = {"hook": hook, "body": body, "cta": cta}
    script_id = sha256_text(f"{hook}\n{body}\n{cta}\n")
    return clip_day, {
        "day": clip_day,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "system": system_id,
        "content_type": "clip",
        "source_video_id": video_id,
        "source_longform_day": day,
        "clip_index": idx,
        "title": hook,
        "angle": "clip",
        "category": "rules_ruling",
        "fact": {"name": hook, "kind": "rule"},
        "script": script,
        "script_id": script_id,
        "youtube_title": yt_title,
        "youtube_description": desc.strip(),
        "content": {"content_id": f"clip:{script_id[:16]}"},
    }


def main():
    system_id = os.environ.get("BIZZAL_SYSTEM_ID", "").strip()
    day = os.environ.get("BIZZAL_LONGFORM_DAY", "").strip()
    video_id = os.environ.get("BIZZAL_LONGFORM_VIDEO_ID", "").strip()
    if not system_id or not day:
        raise SystemExit("[make_clips] ERROR: BIZZAL_SYSTEM_ID and BIZZAL_LONGFORM_DAY required")

    lf_atom_path = os.path.join(
        REPO_ROOT, f"data/atoms_longform_{system_id}/validated/{day}.json"
    )
    if not os.path.exists(lf_atom_path):
        raise SystemExit(f"[make_clips] ERROR: long-form atom missing: {lf_atom_path}")

    lf = load_json(lf_atom_path)
    sections = (lf.get("script") or {}).get("sections") or []
    title = lf.get("youtube_title") or lf.get("title") or ""
    if len(sections) < 2:
        raise SystemExit(f"[make_clips] ERROR: need >= 2 sections, got {len(sections)}")

    n = min(MAX_CLIPS, len(sections))
    sys_label = system_label(system_id)
    print(f"[make_clips] {system_id} {day}: {len(sections)} sections -> up to {n} clips (source video={video_id or 'none'})")

    raw = call_openai(build_prompt(title, sections, sys_label, n))
    clips = parse_clips(raw)
    if not clips:
        raise SystemExit("[make_clips] ERROR: model returned no clips")

    out_dir = os.path.join(REPO_ROOT, f"data/atoms_clips_{system_id}/validated")
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for i, clip in enumerate(clips[:n], start=1):
        if not (clip.get("hook") and clip.get("body")):
            continue
        clip_day, atom = make_clip_atom(system_id, day, clip, i, video_id)
        dst = os.path.join(out_dir, f"{clip_day}.json")
        atomic_write_json(dst, atom)
        written.append(clip_day)
        print(f"[make_clips] clip {i}: {atom['script']['hook']!r} -> {dst}")

    # Emit the clip day-keys so the runner knows what to render.
    manifest = os.path.join(out_dir, f"{day}.manifest.json")
    atomic_write_json(manifest, {"clips": written})
    print(f"[make_clips] wrote {len(written)} clips; manifest={manifest}")
    for c in written:
        print(c)


if __name__ == "__main__":
    main()
