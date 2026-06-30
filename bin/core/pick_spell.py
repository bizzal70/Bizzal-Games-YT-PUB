#!/usr/bin/env python3
import json, os, random, sys
from datetime import datetime

from reference_paths import resolve_active_srd_path

SYSTEM_ID = os.environ.get("BIZZAL_SYSTEM_ID", "").strip()
if not SYSTEM_ID:
    print("ERROR: BIZZAL_SYSTEM_ID is not set. Run via bin/core/system_env.sh <system_id>.", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
REF_CFG = ""  # vestigial: config now comes from the DB via BIZZAL_SYSTEM_ID


def resolve_incoming_dir() -> str:
    val = (os.getenv("BIZZAL_ATOM_INCOMING_DIR") or "").strip()
    if not val:
        return os.path.join(REPO_ROOT, "data", "atoms", "incoming")
    if os.path.isabs(val):
        return val
    return os.path.join(REPO_ROOT, val)


def resolve_day() -> str:
    return (os.getenv("BIZZAL_DAY") or "").strip() or datetime.now().strftime("%Y-%m-%d")


def atom_path(day: str) -> str:
    return os.path.join(resolve_incoming_dir(), day + ".json")

def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def atomic_write_json(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False); f.write("\n")
    os.replace(tmp, p)

def main():
    day = resolve_day()
    path = atom_path(day)
    atom = load_json(path)
    cat = atom.get("category")
    if cat != "spell_use_case":
        print(f"ERROR: pick_spell only supports spell_use_case, got {cat}", file=sys.stderr)
        sys.exit(3)

    active_dir, cfg = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    if not active_dir or not os.path.isdir(active_dir):
        print(f"ERROR: Bad active_srd_path in {REF_CFG}: {active_dir}", file=sys.stderr)
        sys.exit(2)
    spell_file = (cfg.get("sources", {}).get("spells") or {}).get("file", "Spell.json")
    path = os.path.join(active_dir, spell_file)

    records = load_json(path)
    pks = [r.get("pk") for r in records if isinstance(r, dict) and r.get("pk") is not None]

    random.seed(f"{day}|{cat}|spell")
    pk = random.choice(pks)

    atom.setdefault("picks", {})
    atom["picks"]["spell_pk"] = pk
    atomic_write_json(path, atom)
    print(path)

if __name__ == "__main__":
    main()
