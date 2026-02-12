#!/usr/bin/env python3
import json, os, random, sys
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: Missing PyYAML. Install with: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ATOM_PATH = os.path.join(REPO_ROOT, "data", "atoms", "incoming", datetime.now().strftime("%Y-%m-%d") + ".json")
REF_CFG  = os.path.join(REPO_ROOT, "config", "reference_sources.yaml")

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

def main():
    atom = load_json(ATOM_PATH)
    cat = atom.get("category")
    if cat not in ("monster_tactic", "encounter_seed"):
        print(f"ERROR: pick_creature only supports monster_tactic/encounter_seed, got {cat}", file=sys.stderr)
        sys.exit(3)

    cfg = load_yaml(REF_CFG) or {}
    active_dir = cfg.get("active_srd_path")
    creatures_file = (cfg.get("sources", {}).get("creatures") or {}).get("file", "Creature.json")
    path = os.path.join(active_dir, creatures_file)

    records = load_json(path)
    pks = [r.get("pk") for r in records if isinstance(r, dict) and r.get("pk") is not None]

    day = datetime.now().strftime("%Y-%m-%d")
    random.seed(f"{day}|{cat}|creature")
    pk = random.choice(pks)

    atom.setdefault("picks", {})
    atom["picks"]["creature_pk"] = pk

    atomic_write_json(ATOM_PATH, atom)
    print(ATOM_PATH)

if __name__ == "__main__":
    main()
