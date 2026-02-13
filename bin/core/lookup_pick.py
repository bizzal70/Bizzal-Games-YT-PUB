#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: Missing PyYAML. Install with: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

from reference_paths import resolve_active_srd_path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ATOM_PATH = os.path.join(REPO_ROOT, "data", "atoms", "incoming", datetime.now().strftime("%Y-%m-%d") + ".json")
REF_CFG = os.path.join(REPO_ROOT, "config", "reference_sources.yaml")

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def index_by_pk(records):
    idx = {}
    if not isinstance(records, list):
        return idx
    for rec in records:
        if isinstance(rec, dict) and rec.get("pk") is not None:
            idx[rec["pk"]] = rec
    return idx

def main():
    if not os.path.exists(ATOM_PATH):
        print(f"ERROR: Atom not found: {ATOM_PATH}", file=sys.stderr)
        sys.exit(3)

    atom = load_json(ATOM_PATH)
    category = atom.get("category")
    picks = atom.get("picks") or {}

    active_dir, cfg = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    if not active_dir or not os.path.isdir(active_dir):
        print(f"ERROR: Bad active_srd_path in {REF_CFG}: {active_dir}", file=sys.stderr)
        sys.exit(2)
    sources = cfg.get("sources", {})

    # Determine which pick we’re resolving
    if category == "item_spotlight":
        pk = picks.get("item_pk")
        filename = (sources.get("items") or {}).get("file", "Item.json")
        kind = "item"
    elif category == "monster_tactic":
        pk = picks.get("creature_pk")
        filename = (sources.get("creatures") or {}).get("file", "Creature.json")
        kind = "creature"
    elif category == "spell_use_case":
        pk = picks.get("spell_pk")
        filename = (sources.get("spells") or {}).get("file", "Spell.json")
        kind = "spell"
    elif category in ("rules_ruling", "rules_myth"):
        pk = picks.get("rule_pk")
        filename = (sources.get("rules") or {}).get("file", "Rule.json")
        kind = "rule"
    elif category == "character_micro_tip":
        pk = picks.get("class_pk")
        filename = (sources.get("classes") or {}).get("file", "CharacterClass.json")
        kind = "class"
    elif category == "encounter_seed":
        pk = picks.get("creature_pk")
        filename = (sources.get("creatures") or {}).get("file", "Creature.json")
        kind = "creature"
    else:
        print(f"ERROR: Unknown category '{category}'", file=sys.stderr)
        sys.exit(4)

    if pk in (None, 0, ""):
        print(f"ERROR: No pk set for category '{category}'", file=sys.stderr)
        sys.exit(5)

    path = os.path.join(active_dir, filename)
    if not os.path.exists(path):
        print(f"ERROR: Missing source file: {path}", file=sys.stderr)
        sys.exit(6)

    records = load_json(path)
    idx = index_by_pk(records)
    rec = idx.get(pk)
    if not rec:
        print(f"ERROR: pk not found in {filename}: {pk}", file=sys.stderr)
        sys.exit(7)

    fields = rec.get("fields") or {}

    # Minimal “fact card” for downstream script generation
    fact = {
        "kind": kind,
        "pk": pk,
        "name": fields.get("name"),
        "document": fields.get("document"),
        "raw_fields": fields
    }

    print(json.dumps(fact, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
