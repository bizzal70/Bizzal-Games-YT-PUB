#!/usr/bin/env python3
import json
import os
import random
import sys
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    print("ERROR: Missing PyYAML. Install with: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

from reference_paths import resolve_active_srd_path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ATOM_DIR = os.path.join(REPO_ROOT, "data", "atoms", "incoming")
REF_CFG = os.path.join(REPO_ROOT, "config", "reference_sources.yaml")

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def atomic_write_json(path: str, obj: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)

def today_atom_path():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(ATOM_DIR, f"{today}.json")

def fixture_pks(records):
    # Django fixture record: {"model": "...", "pk": 123, "fields": {...}}
    out = []
    if not isinstance(records, list):
        return out
    for rec in records:
        if isinstance(rec, dict) and rec.get("pk") is not None:
            out.append(rec["pk"])
    return out

def pick_pk(active_dir: str, filename: str) -> int:
    path = os.path.join(active_dir, filename)
    if not os.path.exists(path):
        print(f"ERROR: Missing source file: {path}", file=sys.stderr)
        sys.exit(10)
    records = load_json(path)
    pks = fixture_pks(records)
    if not pks:
        print(f"ERROR: No pk records found in: {path}", file=sys.stderr)
        sys.exit(11)
    return random.choice(pks)

def ensure_pick(picks: dict, key: str, value):
    # For creature_pk (0 means unset); for others None means unset
    if key == "creature_pk":
        if picks.get(key) in (None, 0):
            picks[key] = value
    else:
        if picks.get(key) is None:
            picks[key] = value

def canonical_category(category: str) -> str:
    aliases = {
        "gm_tip": "rules_ruling",
        "roleplaying_tip": "character_micro_tip",
        "character_class_spotlight": "character_micro_tip",
        "class_spotlight": "character_micro_tip",
        "dungeoneering_encounter": "encounter_seed",
        "overworld_encounter": "encounter_seed",
    }
    return aliases.get((category or "").strip().lower(), (category or "").strip().lower())

def main():
    random.seed()

    atom_path = today_atom_path()
    if not os.path.exists(atom_path):
        print(f"ERROR: Atom not found: {atom_path}", file=sys.stderr)
        sys.exit(3)

    atom = load_json(atom_path)
    category = canonical_category(atom.get("category"))
    if not category:
        print("ERROR: Atom missing category", file=sys.stderr)
        sys.exit(4)

    active_dir, cfg = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    if not active_dir or not os.path.isdir(active_dir):
        print(f"ERROR: Bad active_srd_path in {REF_CFG}: {active_dir}", file=sys.stderr)
        sys.exit(5)

    sources = cfg.get("sources", {})

    # Resolve filenames from config
    creature_file = (sources.get("creatures") or {}).get("file", "Creature.json")
    spell_file    = (sources.get("spells") or {}).get("file", "Spell.json")
    item_file     = (sources.get("items") or {}).get("file", "Item.json")
    rule_file     = (sources.get("rules") or {}).get("file", "Rule.json")
    class_file    = (sources.get("classes") or {}).get("file", "CharacterClass.json")

    atom.setdefault("picks", {})
    picks = atom["picks"]

    # Fill required picks per category (v1)
    if category == "monster_tactic":
        ensure_pick(picks, "creature_pk", pick_pk(active_dir, creature_file))

    elif category == "spell_use_case":
        ensure_pick(picks, "spell_pk", pick_pk(active_dir, spell_file))

    elif category == "item_spotlight":
        ensure_pick(picks, "item_pk", pick_pk(active_dir, item_file))

    elif category in ("rules_ruling", "rules_myth"):
        ensure_pick(picks, "rule_pk", pick_pk(active_dir, rule_file))

    elif category == "encounter_seed":
        # anchor on a creature; later we can add optional rule_pk, environment, etc.
        ensure_pick(picks, "creature_pk", pick_pk(active_dir, creature_file))

    elif category == "character_micro_tip":
        ensure_pick(picks, "class_pk", pick_pk(active_dir, class_file))

    else:
        print(f"ERROR: Unknown category '{category}'", file=sys.stderr)
        sys.exit(6)

    # Stamp provenance
    atom.setdefault("source", {})
    atom["source"]["active_srd_path"] = active_dir
    atom["source"]["filled_picks_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    atomic_write_json(atom_path, atom)
    print(atom_path)

if __name__ == "__main__":
    main()
