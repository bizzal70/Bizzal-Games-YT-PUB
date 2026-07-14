#!/usr/bin/env python3
import json
import os
import random
import sys
from datetime import datetime, timezone

from reference_paths import resolve_active_srd_path

SYSTEM_ID = os.environ.get("BIZZAL_SYSTEM_ID", "").strip()
if not SYSTEM_ID:
    print("ERROR: BIZZAL_SYSTEM_ID is not set. Run via bin/core/system_env.sh <system_id>.", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def resolve_repo_path(raw: str, default_abs: str) -> str:
    value = (raw or "").strip()
    if not value:
        return default_abs
    if os.path.isabs(value):
        return value
    return os.path.join(REPO_ROOT, value)


ATOM_DIR = resolve_repo_path(os.getenv("BIZZAL_ATOM_INCOMING_DIR", ""), os.path.join(REPO_ROOT, "data", "atoms", "incoming"))
REF_CFG = os.getenv("BIZZAL_REFERENCE_SOURCES_PATH", "").strip() or os.path.join(REPO_ROOT, "config", "reference_sources.yaml")
if not os.path.isabs(REF_CFG):
    REF_CFG = os.path.join(REPO_ROOT, REF_CFG)
VALIDATED_DIR = resolve_repo_path(os.getenv("BIZZAL_ATOM_VALIDATED_DIR", ""), os.path.join(REPO_ROOT, "data", "atoms", "validated"))
STATE_DIR = os.path.join(REPO_ROOT, "data", "state")

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def atomic_write_json(path: str, obj: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)

def today_atom_path():
    day = (os.getenv("BIZZAL_DAY") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    return os.path.join(ATOM_DIR, f"{day}.json")

def fixture_pks(records):
    # Django fixture record: {"model": "...", "pk": 123, "fields": {...}}
    out = []
    if not isinstance(records, list):
        return out
    for rec in records:
        if isinstance(rec, dict) and rec.get("pk") is not None:
            out.append(rec["pk"])
    return out


def normalize_name(value) -> str:
    return str(value or "").strip().lower()


def extract_name_prefix(name: str) -> str:
    """First word of a normalized name for creature subtype grouping.
    E.g. 'ancient' from 'ancient red dragon'. Ignores trivial words (<= 2 chars).
    """
    parts = (name or "").strip().split()
    w = parts[0] if parts else ""
    return w if len(w) > 2 else ""


def validated_atom_paths() -> list[str]:
    if not os.path.isdir(VALIDATED_DIR):
        return []
    out = []
    for name in os.listdir(VALIDATED_DIR):
        if not name.endswith(".json"):
            continue
        out.append(os.path.join(VALIDATED_DIR, name))
    return sorted(out)


def recent_used_pks(pick_key: str, current_day: str, lookback_days: int) -> set:
    if lookback_days <= 0:
        return set()

    paths = validated_atom_paths()
    if not paths:
        return set()

    used = set()
    count = 0
    for path in reversed(paths):
        try:
            atom = load_json(path)
        except Exception:
            continue

        day = str(atom.get("day") or "").strip()
        if day == current_day:
            continue

        picks = atom.get("picks") or {}
        pk = picks.get(pick_key)
        if pk not in (None, "", 0):
            used.add(pk)

        count += 1
        if count >= lookback_days:
            break

    return used


def recent_used_fact_names(current_day: str, lookback_days: int, categories: set[str]) -> set[str]:
    if lookback_days <= 0:
        return set()

    paths = validated_atom_paths()
    if not paths:
        return set()

    used = set()
    count = 0
    canonical_categories = {canonical_category(c) for c in categories}
    for path in reversed(paths):
        try:
            atom = load_json(path)
        except Exception:
            continue

        day = str(atom.get("day") or "").strip()
        if day == current_day:
            continue

        category = canonical_category(atom.get("category") or "")
        if category not in canonical_categories:
            count += 1
            if count >= lookback_days:
                break
            continue

        fact = atom.get("fact") or {}
        name = normalize_name(fact.get("name"))
        if name:
            used.add(name)

        count += 1
        if count >= lookback_days:
            break

    return used


def registry_used_fact_names(categories: set[str]) -> set[str]:
    """Read the permanent publish registry and return all ever-published fact names
    for the given categories. This is the long-term dedup layer -- validated atoms
    are ephemeral (runner temp) but the registry is committed back to the repo."""
    registry_path = os.path.join(STATE_DIR, f"published_registry_{SYSTEM_ID}.json")
    if not os.path.exists(registry_path):
        return set()

    try:
        data = load_json(registry_path)
    except Exception:
        return set()

    items = data if isinstance(data, list) else (data.get("items") or [])
    canonical_categories = {canonical_category(c) for c in categories}
    used: set[str] = set()

    for entry in items:
        if not isinstance(entry, dict):
            continue
        fp = entry.get("fingerprint") or entry
        cat = canonical_category(str(fp.get("category") or ""))
        if cat not in canonical_categories:
            continue
        name = normalize_name(fp.get("fact_name") or "")
        if name:
            used.add(name)

    return used


def registry_used_name_prefixes(categories: set[str]) -> set[str]:
    """
    Return first-word prefixes of published creature fact names in given categories.
    Prevents e.g. 'Ancient Red Dragon' then 'Ancient Blue Dragon' on consecutive same-DOW runs.
    """
    registry_path = os.path.join(STATE_DIR, f"published_registry_{SYSTEM_ID}.json")
    if not os.path.exists(registry_path):
        return set()
    try:
        data = load_json(registry_path)
    except Exception:
        return set()
    items = data if isinstance(data, list) else (data.get("items") or [])
    canonical_categories = {canonical_category(c) for c in categories}
    prefixes: set[str] = set()
    for entry in items:
        if not isinstance(entry, dict):
            continue
        fp = entry.get("fingerprint") or entry
        cat = canonical_category(str(fp.get("category") or ""))
        if cat not in canonical_categories:
            continue
        name = normalize_name(fp.get("fact_name") or "")
        prefix = extract_name_prefix(name)
        if prefix:
            prefixes.add(prefix)
    return prefixes


def choose_pk_with_variety(candidates: list, avoid: set):
    if not candidates:
        return None
    filtered = [pk for pk in candidates if pk not in avoid]
    pool = filtered if filtered else candidates
    return random.choice(pool)


def pick_candidate_pk(candidates: list[tuple[int, str]], avoid_pks: set | None = None, avoid_names: set | None = None, avoid_prefixes: set | None = None):
    if not candidates:
        return None

    avoid_pks = avoid_pks or set()
    avoid_names = avoid_names or set()
    avoid_prefixes = avoid_prefixes or set()

    # Primary: avoid pks, names, AND subtype prefix
    primary = [
        (pk, name) for pk, name in candidates
        if pk not in avoid_pks
        and normalize_name(name) not in avoid_names
        and extract_name_prefix(normalize_name(name)) not in avoid_prefixes
    ]
    if primary:
        return random.choice(primary)[0]

    # Secondary: relax prefix constraint
    secondary = [(pk, name) for pk, name in candidates if pk not in avoid_pks and normalize_name(name) not in avoid_names]
    if secondary:
        return random.choice(secondary)[0]

    # Tertiary: only avoid exact pk collision
    tertiary = [(pk, name) for pk, name in candidates if pk not in avoid_pks]
    if tertiary:
        return random.choice(tertiary)[0]

    return random.choice(candidates)[0]

def pick_pk(active_dir: str, filename: str, avoid: set | None = None, avoid_names: set | None = None) -> int:
    path = os.path.join(active_dir, filename)
    if not os.path.exists(path):
        print(f"ERROR: Missing source file: {path}", file=sys.stderr)
        sys.exit(10)
    records = load_json(path)
    candidates = []
    if isinstance(records, list):
        for rec in records:
            if not isinstance(rec, dict):
                continue
            pk = rec.get("pk")
            if pk is None:
                continue
            fields = rec.get("fields") or {}
            candidates.append((pk, str(fields.get("name") or "")))

    if not candidates:
        print(f"ERROR: No pk records found in: {path}", file=sys.stderr)
        sys.exit(11)

    pick = pick_candidate_pk(candidates, avoid or set(), avoid_names or set())
    if pick is None:
        print(f"ERROR: Unable to choose pk from: {path}", file=sys.stderr)
        sys.exit(12)
    return pick

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

def creature_is_weak_moral_choice_candidate(rec: dict) -> bool:
    fields = (rec or {}).get("fields") or {}
    name = str(fields.get("name") or "").strip().lower()
    ctype = str(fields.get("type") or fields.get("creature_type") or "").strip().lower()
    cr = parse_cr(fields.get("challenge_rating") or fields.get("cr"))

    if not name:
        return False

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

def pick_creature_pk(
    active_dir: str,
    filename: str,
    category: str,
    angle: str,
    avoid: set | None = None,
    avoid_names: set | None = None,
    avoid_prefixes: set | None = None,
) -> int:
    path = os.path.join(active_dir, filename)
    if not os.path.exists(path):
        print(f"ERROR: Missing source file: {path}", file=sys.stderr)
        sys.exit(10)

    records = load_json(path)
    if not isinstance(records, list):
        print(f"ERROR: Creature source is not a list: {path}", file=sys.stderr)
        sys.exit(11)

    all_candidates: list[tuple[int, str]] = []
    filtered_candidates: list[tuple[int, str]] = []
    cat = (category or "").strip().lower()
    ang = (angle or "").strip().lower()

    for rec in records:
        if not isinstance(rec, dict) or rec.get("pk") is None:
            continue
        pk = rec["pk"]
        name = str(((rec.get("fields") or {}).get("name") or ""))
        all_candidates.append((pk, name))

        if cat == "encounter_seed" and ang == "moral_choice" and creature_is_weak_moral_choice_candidate(rec):
            continue
        filtered_candidates.append((pk, name))

    if not filtered_candidates:
        filtered_candidates = all_candidates

    if not filtered_candidates:
        print(f"ERROR: No creature pk records found in: {path}", file=sys.stderr)
        sys.exit(12)

    pick = pick_candidate_pk(filtered_candidates, avoid or set(), avoid_names or set(), avoid_prefixes or set())
    if pick is None:
        print(f"ERROR: Unable to choose creature pk from: {path}", file=sys.stderr)
        sys.exit(13)
    return pick

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
    atom_path = today_atom_path()
    if not os.path.exists(atom_path):
        print(f"ERROR: Atom not found: {atom_path}", file=sys.stderr)
        sys.exit(3)

    atom = load_json(atom_path)
    day = (atom.get("day") or (os.getenv("BIZZAL_DAY") or "").strip() or datetime.now().strftime("%Y-%m-%d"))
    category = canonical_category(atom.get("category"))
    angle = (atom.get("angle") or "").strip().lower()
    if not category:
        print("ERROR: Atom missing category", file=sys.stderr)
        sys.exit(4)

    random.seed(f"{day}|{category}|{angle}|fill_picks")

    try:
        lookback_days = int((os.getenv("BIZZAL_VARIETY_LOOKBACK_DAYS") or "14").strip())
    except ValueError:
        lookback_days = 14
    if lookback_days < 0:
        lookback_days = 0

    try:
        name_lookback_days = int((os.getenv("BIZZAL_VARIETY_NAME_LOOKBACK_DAYS") or str(lookback_days)).strip())
    except ValueError:
        name_lookback_days = lookback_days
    if name_lookback_days < 0:
        name_lookback_days = 0

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

    # Short-term PK avoidance from local validated atoms (ephemeral, best-effort)
    avoid_creature = recent_used_pks("creature_pk", day, lookback_days)
    avoid_spell = recent_used_pks("spell_pk", day, lookback_days)
    avoid_item = recent_used_pks("item_pk", day, lookback_days)
    avoid_rule = recent_used_pks("rule_pk", day, lookback_days)
    avoid_class = recent_used_pks("class_pk", day, lookback_days)

    # Short-term name avoidance from local validated atoms
    avoid_creature_names = recent_used_fact_names(day, name_lookback_days, {"monster_tactic", "encounter_seed"})
    avoid_spell_names = recent_used_fact_names(day, name_lookback_days, {"spell_use_case"})
    avoid_item_names = recent_used_fact_names(day, name_lookback_days, {"item_spotlight"})
    avoid_rule_names = recent_used_fact_names(day, name_lookback_days, {"rules_ruling", "rules_myth"})
    avoid_class_names = recent_used_fact_names(day, name_lookback_days, {"character_micro_tip"})

    # Permanent name avoidance from the publish registry (committed back to repo).
    # This ensures we never cover the same topic twice regardless of how long ago it ran.
    avoid_creature_names |= registry_used_fact_names({"monster_tactic", "encounter_seed"})
    avoid_spell_names    |= registry_used_fact_names({"spell_use_case"})
    avoid_item_names     |= registry_used_fact_names({"item_spotlight"})
    avoid_rule_names     |= registry_used_fact_names({"rules_ruling", "rules_myth"})
    avoid_class_names    |= registry_used_fact_names({"character_micro_tip"})

    # Subtype prefix avoidance for creatures -- prevents e.g. Ancient Red then Ancient Blue
    # on consecutive same-DOW runs. Falls back gracefully if all prefixes exhausted.
    avoid_creature_prefixes = registry_used_name_prefixes({"monster_tactic", "encounter_seed"})

    # Fill required picks per category (v1)
    if category == "monster_tactic":
        ensure_pick(
            picks,
            "creature_pk",
            pick_creature_pk(active_dir, creature_file, category, angle, avoid_creature, avoid_creature_names, avoid_creature_prefixes),
        )

    elif category == "spell_use_case":
        ensure_pick(picks, "spell_pk", pick_pk(active_dir, spell_file, avoid_spell, avoid_spell_names))

    elif category == "item_spotlight":
        ensure_pick(picks, "item_pk", pick_pk(active_dir, item_file, avoid_item, avoid_item_names))

    elif category in ("rules_ruling", "rules_myth"):
        ensure_pick(picks, "rule_pk", pick_pk(active_dir, rule_file, avoid_rule, avoid_rule_names))

    elif category == "encounter_seed":
        # anchor on a creature; later we can add optional rule_pk, environment, etc.
        ensure_pick(
            picks,
            "creature_pk",
            pick_creature_pk(active_dir, creature_file, category, angle, avoid_creature, avoid_creature_names, avoid_creature_prefixes),
        )

    elif category == "character_micro_tip":
        ensure_pick(picks, "class_pk", pick_pk(active_dir, class_file, avoid_class, avoid_class_names))

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
