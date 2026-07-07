#!/usr/bin/env python3
"""
make_longform_atom.py — build a long-form atom from the topic queue.

Pops the next pending brief for the current system from topic_queue.json,
runs write_longform_script.py to produce a full ~1,400 word structured script,
then validates and writes the atom to data/atoms_longform_{system}/incoming/.

Usage: python bin/longform/make_longform_atom.py [--day YYYY-MM-DD]
"""
import sys, os, json, hashlib, argparse, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../core"))

from datetime import datetime, UTC

import system_config

SYSTEM_ID = os.environ.get("BIZZAL_SYSTEM_ID", "").strip()
if not SYSTEM_ID:
    raise SystemExit("ERROR: BIZZAL_SYSTEM_ID is not set.")

REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DATA_DIR   = os.path.join(REPO_ROOT, "data")
QUEUE_PATH = os.path.join(DATA_DIR, "longform", "topic_queue.json")


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


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def incoming_dir() -> str:
    return os.path.join(DATA_DIR, f"atoms_longform_{SYSTEM_ID}", "incoming")


def validated_dir() -> str:
    return os.path.join(DATA_DIR, f"atoms_longform_{SYSTEM_ID}", "validated")


def failed_dir() -> str:
    return os.path.join(DATA_DIR, f"atoms_longform_{SYSTEM_ID}", "failed")


def atom_path(day: str) -> str:
    return os.path.join(incoming_dir(), f"{day}.json")


def pop_next_brief(system_id: str) -> dict | None:
    """Find the next pending brief for this system, mark it in_progress."""
    if not os.path.exists(QUEUE_PATH):
        return None
    queue = load_json(QUEUE_PATH)
    if not isinstance(queue, list):
        return None
    for i, b in enumerate(queue):
        if b.get("system") == system_id and b.get("status") == "pending":
            queue[i]["status"] = "in_progress"
            atomic_write_json(QUEUE_PATH, queue)
            return b
    return None


def mark_brief_done(brief_id: str, status: str = "used"):
    if not os.path.exists(QUEUE_PATH):
        return
    queue = load_json(QUEUE_PATH)
    for b in queue:
        if b.get("brief_id") == brief_id:
            b["status"] = status
            break
    atomic_write_json(QUEUE_PATH, queue)


def run_step(script_path: str, env_extra: dict = None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([sys.executable, script_path], cwd=REPO_ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit(f"[make_longform_atom] step failed ({r.returncode}): {script_path}")


def minimal_validate(atom: dict) -> tuple[bool, str]:
    required = ["day", "created_at", "system", "brief_id", "title", "angle",
                "fixture_hint", "script", "script_id", "content_type"]
    for k in required:
        if k not in atom:
            return False, f"missing key: {k}"

    script = atom.get("script", {})
    if not isinstance(script, dict):
        return False, "script not dict"

    required_script = ["intro", "sections", "outro"]
    for k in required_script:
        if k not in script or not str(script.get(k, "")).strip():
            return False, f"script missing: {k}"

    sections = script.get("sections", [])
    if not isinstance(sections, list) or len(sections) < 3:
        return False, f"script.sections too short (got {len(sections)}, need >= 3)"

    # script_id integrity
    packed = f"{script.get('intro','').strip()}\n{json.dumps(sections)}\n{script.get('outro','').strip()}\n"
    expected = sha256_text(packed)
    if atom.get("script_id") != expected:
        return False, "script_id mismatch"

    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="")
    args = ap.parse_args()
    day = args.day.strip() or datetime.now(UTC).strftime("%Y-%m-%d")
    os.environ["BIZZAL_DAY"] = day

    os.makedirs(incoming_dir(), exist_ok=True)
    os.makedirs(validated_dir(), exist_ok=True)
    os.makedirs(failed_dir(), exist_ok=True)

    brief = pop_next_brief(SYSTEM_ID)
    if brief is None:
        raise SystemExit(f"[make_longform_atom] no pending briefs for {SYSTEM_ID} in {QUEUE_PATH}")

    print(f"[make_longform_atom] system={SYSTEM_ID} day={day}")
    print(f"[make_longform_atom] brief: {brief.get('title')} ({brief.get('brief_id')})")

    atom = {
        "day": day,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "system": SYSTEM_ID,
        "content_type": "longform",
        "brief_id": brief.get("brief_id"),
        "title": brief.get("title"),
        "angle": brief.get("angle"),
        "rationale": brief.get("rationale"),
        "fixture_hint": brief.get("fixture_hint"),
        "search_keyword": brief.get("search_keyword"),
        "script": {},
        "script_id": None,
    }
    atomic_write_json(atom_path(day), atom)

    # Write brief to env so write_longform_script.py can read it
    os.environ["BIZZAL_LONGFORM_BRIEF"] = json.dumps(brief)
    os.environ["BIZZAL_LONGFORM_ATOM_PATH"] = atom_path(day)

    # Generate the script
    script_writer = os.path.join(REPO_ROOT, "bin", "longform", "write_longform_script.py")
    run_step(script_writer)

    # Reload and validate
    atom = load_json(atom_path(day))
    ok, msg = minimal_validate(atom)

    if ok:
        dst = os.path.join(validated_dir(), f"{day}.json")
        os.replace(atom_path(day), dst)
        mark_brief_done(brief.get("brief_id"), "used")
        print(f"[make_longform_atom] validated → {dst}")
        print(dst)
        return

    # Failure path
    atom.setdefault("errors", [])
    atom["errors"].append({
        "at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "error": msg,
    })
    atomic_write_json(atom_path(day), atom)
    dst = os.path.join(failed_dir(), f"{day}.json")
    os.replace(atom_path(day), dst)
    mark_brief_done(brief.get("brief_id"), "failed")
    raise SystemExit(f"[make_longform_atom] validation failed: {msg}")


if __name__ == "__main__":
    main()
