#!/usr/bin/env python3
import json, os, sys
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: Missing PyYAML. Install with: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

from reference_paths import resolve_active_srd_path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ATOM_PATH = os.path.join(REPO_ROOT, "data", "atoms", "incoming", datetime.now().strftime("%Y-%m-%d") + ".json")
REF_CFG  = os.path.join(REPO_ROOT, "config", "reference_sources.yaml")

def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def load_yaml(p):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def atomic_write_json(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False); f.write("\n")
    os.replace(tmp, p)

def index_by_pk(records):
    out = {}
    if isinstance(records, list):
        for r in records:
            if isinstance(r, dict) and r.get("pk") is not None:
                out[r["pk"]] = r
    return out

def group_by_parent(records):
    out = {}
    if isinstance(records, list):
        for r in records:
            if not isinstance(r, dict): 
                continue
            fields = r.get("fields") or {}
            parent = fields.get("parent")
            if parent is None:
                continue
            out.setdefault(parent, []).append(r)
    return out

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
    atom = load_json(ATOM_PATH)
    category = canonical_category(atom.get("category"))
    picks = atom.get("picks") or {}

    active_dir, cfg = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    sources = cfg.get("sources", {})

    if not active_dir or not os.path.isdir(active_dir):
        print(f"ERROR: Bad active_srd_path in {REF_CFG}: {active_dir}", file=sys.stderr)
        sys.exit(2)

    # Map category -> kind/pk/file
    if category == "item_spotlight":
        kind, pk = "item", picks.get("item_pk")
        base_file = (sources.get("items") or {}).get("file", "Item.json")
    elif category == "spell_use_case":
        kind, pk = "spell", picks.get("spell_pk")
        base_file = (sources.get("spells") or {}).get("file", "Spell.json")
    elif category in ("monster_tactic", "encounter_seed"):
        kind, pk = "creature", picks.get("creature_pk")
        base_file = (sources.get("creatures") or {}).get("file", "Creature.json")
    elif category in ("rules_ruling", "rules_myth"):
        kind, pk = "rule", picks.get("rule_pk")
        base_file = (sources.get("rules") or {}).get("file", "Rule.json")
    elif category == "character_micro_tip":
        kind, pk = "class", picks.get("class_pk")
        base_file = (sources.get("classes") or {}).get("file", "CharacterClass.json")
    else:
        print(f"ERROR: Unsupported category '{category}' for attach_fact", file=sys.stderr)
        sys.exit(3)

    if pk in (None, 0, ""):
        print(f"ERROR: Missing pk for {category}", file=sys.stderr)
        sys.exit(4)

    base_path = os.path.join(active_dir, base_file)
    base_rec = index_by_pk(load_json(base_path)).get(pk)
    if not base_rec:
        print(f"ERROR: pk not found in {base_file}: {pk}", file=sys.stderr)
        sys.exit(5)

    base_fields = base_rec.get("fields") or {}

    fact = {
        "kind": kind,
        "pk": pk,
        "name": base_fields.get("name"),
        "document": base_fields.get("document"),
        "fields": base_fields,
    }

    # Creature bundle joins
    if kind == "creature":
        trait_file  = (sources.get("creature_traits") or {}).get("file", "CreatureTrait.json")
        action_file = (sources.get("creature_actions") or {}).get("file", "CreatureAction.json")
        atk_file    = (sources.get("creature_attacks") or {}).get("file", "CreatureActionAttack.json")

        trait_path  = os.path.join(active_dir, trait_file)
        action_path = os.path.join(active_dir, action_file)
        atk_path    = os.path.join(active_dir, atk_file)

        traits_all  = load_json(trait_path)
        actions_all = load_json(action_path)
        atks_all    = load_json(atk_path)

        traits = (group_by_parent(traits_all).get(pk) or [])
        actions = (group_by_parent(actions_all).get(pk) or [])
        attacks = (group_by_parent(atks_all).get(pk) or [])

        # Attach only fields (keep it lightweight)
        fact["traits"] = [t.get("fields") or {} for t in traits]
        fact["actions"] = [a.get("fields") or {} for a in actions]
        fact["attacks"] = [x.get("fields") or {} for x in attacks]

    # Spell joins (optional files; attach only if present)
    if kind == "spell":
        def try_load(path):
            try:
                return load_json(path)
            except Exception:
                return None

        sco_file = (sources.get("spell_casting_options") or {}).get("file", "SpellCastingOption.json")
        sl_file  = (sources.get("spell_lists") or {}).get("file", "SpellList.json")

        sco_path = os.path.join(active_dir, sco_file)
        sl_path  = os.path.join(active_dir, sl_file)

        sco_all = try_load(sco_path)
        sl_all  = try_load(sl_path)

        # These datasets usually reference spell by parent; if not, we'll just skip.
        if isinstance(sco_all, list):
            sco = (group_by_parent(sco_all).get(pk) or [])
            fact["casting_options"] = [x.get("fields") or {} for x in sco]
        if isinstance(sl_all, list):
            sl = (group_by_parent(sl_all).get(pk) or [])
            fact["spell_lists"] = [x.get("fields") or {} for x in sl]

    atom["fact"] = fact
    atomic_write_json(ATOM_PATH, atom)
    print(ATOM_PATH)

if __name__ == "__main__":
    main()
