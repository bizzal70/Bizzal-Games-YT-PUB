#!/usr/bin/env python3
"""
make_longform_atom.py -- build an SRD-GROUNDED long-form atom.

REWRITTEN 2026-07-22 after the confabulation incident. The old version popped a
NEWS brief from topic_queue.json and asked the model to invent rules to fit it,
which shipped fabricated content ("Godzilla in D&D", "Shadowdark Summoner"). The
new version mirrors the Shorts pipeline, which never confabulated because it is
grounded: it selects a REAL fixture entity (creature/class/spell) from
reference/systems/<sys>/active/* via attach_fact.py, then expands that real,
assembled fact into an 8-10 minute deep dive. The subject and every mechanic come
from your corpus; nothing is invented.

Public sources still get leverage -- a pending news brief's `fixture_hint` biases
WHICH kind of real entity we feature today (so the topic stays timely) -- but the
content is always a real fixture entity, never the headline itself.

Pipeline: pick real pk -> attach_fact.py (assemble) -> write_longform_script.py
(deep dive) -> structural validate -> IP scan -> SRD canon check -> validated/.

Usage: python bin/longform/make_longform_atom.py [--day YYYY-MM-DD]
"""
import sys, os, json, hashlib, argparse, subprocess, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../core"))

from datetime import datetime, UTC

import content_safety
import system_config
from reference_paths import resolve_active_srd_path

SYSTEM_ID = os.environ.get("BIZZAL_SYSTEM_ID", "").strip()
if not SYSTEM_ID:
    raise SystemExit("ERROR: BIZZAL_SYSTEM_ID is not set.")

REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DATA_DIR   = os.path.join(REPO_ROOT, "data")
QUEUE_PATH = os.path.join(DATA_DIR, "longform", "topic_queue.json")
REF_CFG    = ""  # resolve_active_srd_path resolves via BIZZAL_SYSTEM_ID

SYSTEM_LABELS = {"dnd5e": "D&D 5e (2024 rules)", "shadowdark": "Shadowdark RPG",
                 "dcc": "Dungeon Crawl Classics RPG"}

# Depth-rich kinds that sustain 8-10 minutes. Each maps to the attach_fact
# category + picks key + fixture file. (Items/rules are thinner; left out of the
# rotation for long-form, though a brief may still request them.)
KIND = {
    "creature": ("monster_tactic",      "creature_pk", "Creature.json"),
    "class":    ("character_micro_tip",  "class_pk",    "CharacterClass.json"),
    "spell":    ("spell_use_case",       "spell_pk",    "Spell.json"),
    "item":     ("item_spotlight",       "item_pk",     "Item.json"),
    "rule":     ("rules_ruling",         "rule_pk",     "Rule.json"),
}
ROTATION = ["creature", "class", "spell"]
HINT_TO_KIND = {"creature": "creature", "monster": "creature", "class": "class",
                "spell": "spell", "item": "item", "rule": "rule"}
SRC_KEY = {"creature": "creatures", "class": "classes", "spell": "spells",
           "item": "items", "rule": "rules"}


def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_text(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()


def incoming_dir():  return os.path.join(DATA_DIR, f"atoms_longform_{SYSTEM_ID}", "incoming")
def validated_dir(): return os.path.join(DATA_DIR, f"atoms_longform_{SYSTEM_ID}", "validated")
def failed_dir():    return os.path.join(DATA_DIR, f"atoms_longform_{SYSTEM_ID}", "failed")
def atom_path(day):  return os.path.join(incoming_dir(), f"{day}.json")


# --------------------------------------------------------------------- selection
def _used_state_path():
    return os.path.join(DATA_DIR, "state", f"longform_srd_used_{SYSTEM_ID}.json")


def _load_used():
    try:
        return load_json(_used_state_path())
    except Exception:
        return {}


def _save_used(used):
    atomic_write_json(_used_state_path(), used)


def _parse_cr(v):
    s = str(v or "").strip().lower()
    if not s:
        return 0.0
    try:
        if "/" in s:
            a, b = s.split("/", 1); return float(a) / float(b)
        return float(s)
    except Exception:
        return 0.0


def pop_brief_hint():
    """Consume a pending news brief (if any) and return its fixture_hint so the
    video KIND stays topical. The brief never supplies content -- only a hint about
    which kind of real fixture entity to feature. Returns (kind, brief_id)."""
    if not os.path.exists(QUEUE_PATH):
        return None, None
    try:
        queue = load_json(QUEUE_PATH)
    except Exception:
        return None, None
    if not isinstance(queue, list):
        return None, None
    chosen = (None, None)
    dirty = False
    for b in queue:
        if b.get("system") == SYSTEM_ID and b.get("status") == "pending":
            ok, _ = content_safety.brief_is_safe(b)
            if not ok:
                b["status"] = "blocked"; dirty = True
                continue
            chosen = (HINT_TO_KIND.get((b.get("fixture_hint") or "").strip().lower()),
                      b.get("brief_id"))
            b["status"] = "used"; dirty = True
            break
    if dirty:
        atomic_write_json(QUEUE_PATH, queue)
    return chosen


def choose_kind(day, hint):
    if hint in KIND:
        return hint
    idx = datetime.strptime(day, "%Y-%m-%d").toordinal() % len(ROTATION)
    return ROTATION[idx]


def select_entity(day, kind):
    """Pick a REAL, unused fixture pk for `kind`. Returns (pk, name) or (None,None).
    Creatures are chosen from the higher-CR pool (more actions/traits => enough
    material for 8-10 min)."""
    _cat, _pick_key, base_file = KIND[kind]
    active_dir, cfg = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    if not active_dir or not os.path.isdir(active_dir):
        raise SystemExit(f"[make_longform_atom] bad active_srd_path: {active_dir}")
    fname = ((cfg.get("sources", {}).get(SRC_KEY[kind]) or {}).get("file")) or base_file
    records = load_json(os.path.join(active_dir, fname))
    cands = [(r["pk"], (r.get("fields") or {}).get("name") or "",
              _parse_cr((r.get("fields") or {}).get("challenge_rating")
                        or (r.get("fields") or {}).get("cr")))
             for r in records if isinstance(r, dict) and r.get("pk") is not None]
    if not cands:
        return None, None

    used = _load_used()
    used_pks = set(used.get(kind, []))
    pool = [c for c in cands if c[0] not in used_pks]
    if not pool:
        used[kind] = []
        pool = cands

    rnd = random.Random(f"{day}|{SYSTEM_ID}|{kind}")
    if kind == "creature":
        pool.sort(key=lambda c: c[2], reverse=True)
        top = pool[:max(8, len(pool) // 4)] or pool
        pk, name, _ = rnd.choice(top)
    else:
        pk, name, _ = rnd.choice(pool)

    used.setdefault(kind, []).append(pk)
    _save_used(used)
    return pk, name


def run_step(script_path, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([sys.executable, script_path], cwd=REPO_ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit(f"[make_longform_atom] step failed ({r.returncode}): {script_path}")


def minimal_validate(atom):
    for k in ("day", "system", "content_type", "fact", "script", "script_id"):
        if k not in atom:
            return False, f"missing key: {k}"
    if not isinstance(atom.get("fact"), dict) or not atom["fact"].get("name"):
        return False, "fact missing/nameless (not grounded)"
    script = atom.get("script", {})
    if not isinstance(script, dict):
        return False, "script not dict"
    for k in ("intro", "sections", "outro"):
        if k not in script or not str(script.get(k, "")).strip():
            return False, f"script missing: {k}"
    sections = script.get("sections", [])
    if not isinstance(sections, list) or len(sections) < 3:
        return False, f"script.sections too short (got {len(sections)}, need >= 3)"
    packed = f"{script.get('intro','').strip()}\n{json.dumps(sections)}\n{script.get('outro','').strip()}\n"
    if atom.get("script_id") != sha256_text(packed):
        return False, "script_id mismatch"
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="")
    args = ap.parse_args()
    day = args.day.strip() or datetime.now(UTC).strftime("%Y-%m-%d")
    os.environ["BIZZAL_DAY"] = day

    for d in (incoming_dir(), validated_dir(), failed_dir()):
        os.makedirs(d, exist_ok=True)

    hint, brief_id = pop_brief_hint()
    kind = choose_kind(day, hint)
    category, pick_key, _ = KIND[kind]

    pk, name = select_entity(day, kind)
    if pk is None:
        raise SystemExit(f"[make_longform_atom] no fixture entities for kind={kind}")
    print(f"[make_longform_atom] system={SYSTEM_ID} day={day} kind={kind} "
          f"pk={pk} name={name!r} (hint={hint}, brief={brief_id})")

    atom = {
        "day": day,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "system": SYSTEM_ID,
        "content_type": "longform",
        "category": category,
        "angle": "deep_dive",
        "kind": kind,
        "picks": {pick_key: pk},
        "brief_id": brief_id,
        "script": {},
        "script_id": None,
    }
    atomic_write_json(atom_path(day), atom)

    def _reject(status, msg):
        a = load_json(atom_path(day))
        a.setdefault("errors", []).append({
            "at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "error": msg})
        atomic_write_json(atom_path(day), a)
        os.replace(atom_path(day), os.path.join(failed_dir(), f"{day}.json"))
        raise SystemExit(f"[make_longform_atom] {msg}")

    # 1) assemble the real fact (base record + creature traits/actions/attacks)
    try:
        run_step(os.path.join(REPO_ROOT, "bin", "core", "attach_fact.py"))
    except SystemExit as exc:
        _reject("failed", f"attach_fact failed: {exc}")

    # 2) deep-dive script from the real fact
    os.environ["BIZZAL_LONGFORM_ATOM_PATH"] = atom_path(day)
    try:
        run_step(os.path.join(REPO_ROOT, "bin", "longform", "write_longform_script.py"))
    except SystemExit as exc:
        _reject("failed", f"script generation failed: {exc}")

    atom = load_json(atom_path(day))

    ok, msg = minimal_validate(atom)
    if not ok:
        _reject("failed", f"validation failed: {msg}")

    # 3) deterministic IP hard-block (final title + body)
    _s = atom.get("script", {}) if isinstance(atom.get("script"), dict) else {}
    _safe, _hits = content_safety.scan_text(" ".join([
        atom.get("youtube_title", "") or "", _s.get("hook", "") or "", _s.get("body", "") or ""]))
    if not _safe:
        _reject("blocked", f"content safety: blocked property/system {_hits}")

    # 4) SRD-grounded canon fact-check. Advisory by default (the LLM is unreliable
    # on fine mechanics; content is grounded by construction). Set
    # BIZZAL_CANON_HARD_BLOCK=1 to refuse publish when grounded=False.
    label = SYSTEM_LABELS.get(SYSTEM_ID, SYSTEM_ID)
    ref = content_safety.srd_digest(SYSTEM_ID, REPO_ROOT)
    body = _s.get("body", "") or ""
    verdict = content_safety.canon_check(body, label, reference=ref)
    if verdict.available:
        print(f"[make_longform_atom] canon grounded={verdict.grounded} "
              f"verdict={verdict.verdict!r} problems={verdict.problems}")
        if not verdict.grounded and os.environ.get("BIZZAL_CANON_HARD_BLOCK") == "1":
            _reject("blocked", f"canon: not grounded -- {verdict.verdict}")
    else:
        print("[make_longform_atom] canon check unavailable (advisory only)")

    dst = os.path.join(validated_dir(), f"{day}.json")
    os.replace(atom_path(day), dst)
    print(f"[make_longform_atom] validated -> {dst}")
    print(dst)


if __name__ == "__main__":
    main()
