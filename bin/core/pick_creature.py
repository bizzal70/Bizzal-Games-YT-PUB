#!/usr/bin/env python3
import json, os, random, sys
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: Missing PyYAML. Install with: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

from reference_paths import resolve_active_srd_path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
REF_CFG  = os.path.join(REPO_ROOT, "config", "reference_sources.yaml")


def resolve_day() -> str:
    return (os.getenv("BIZZAL_DAY") or "").strip() or datetime.now().strftime("%Y-%m-%d")


def atom_path(day: str) -> str:
    return os.path.join(REPO_ROOT, "data", "atoms", "incoming", day + ".json")

def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def atomic_write_json(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False); f.write("\n")
    os.replace(tmp, p)

def load_yaml(p):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def parse_cr(value) -> float:
    if value is None:
        return 0.0
    s = str(value).strip().lower()
    if not s:
        return 0.0
    try:
        if "/" in s:
            a, b = s.split("/", 1)
            return float(a) / float(b)
        return float(s)
    except Exception:
        return 0.0

def weak_moral_choice_candidate(rec: dict) -> bool:
    fields = (rec or {}).get("fields") or {}
    name = str(fields.get("name") or "").strip().lower()
    ctype = str(fields.get("type") or fields.get("creature_type") or "").strip().lower()
    cr = parse_cr(fields.get("challenge_rating") or fields.get("cr"))

    mundane_mount_tokens = (
        "riding horse", "draft horse", "pony", "mule", "donkey", "camel", "ox", "goat", "mastiff"
    )
    high_fantasy_exceptions = ("nightmare", "pegasus", "unicorn")

    if any(tok in name for tok in mundane_mount_tokens) and not any(tok in name for tok in high_fantasy_exceptions):
        return True
    if ctype in ("beast", "animal") and cr <= 0.25:
        return True
    if cr == 0.0:
        return True
    return False

def main():
    day = resolve_day()
    path = atom_path(day)
    atom = load_json(path)
    cat = atom.get("category")
    if cat not in ("monster_tactic", "encounter_seed"):
        print(f"ERROR: pick_creature only supports monster_tactic/encounter_seed, got {cat}", file=sys.stderr)
        sys.exit(3)

    active_dir, cfg = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    if not active_dir or not os.path.isdir(active_dir):
        print(f"ERROR: Bad active_srd_path in {REF_CFG}: {active_dir}", file=sys.stderr)
        sys.exit(2)
    creatures_file = (cfg.get("sources", {}).get("creatures") or {}).get("file", "Creature.json")
    path = os.path.join(active_dir, creatures_file)

    records = load_json(path)
    pks = [r.get("pk") for r in records if isinstance(r, dict) and r.get("pk") is not None]

    angle = (atom.get("angle") or "").strip().lower()
    if cat == "encounter_seed" and angle == "moral_choice":
        filtered = [
            r.get("pk") for r in records
            if isinstance(r, dict) and r.get("pk") is not None and not weak_moral_choice_candidate(r)
        ]
        if filtered:
            pks = filtered

    random.seed(f"{day}|{cat}|creature")
    pk = random.choice(pks)

    atom.setdefault("picks", {})
    atom["picks"]["creature_pk"] = pk

    atomic_write_json(path, atom)
    print(path)

if __name__ == "__main__":
    main()
