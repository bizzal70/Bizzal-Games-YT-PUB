#!/usr/bin/env python3
import hashlib, json, os, sys, re
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: Missing PyYAML. Install with: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ATOM_PATH = os.path.join(REPO_ROOT, "data", "atoms", "incoming", datetime.now().strftime("%Y-%m-%d") + ".json")
STYLE_CFG = os.path.join(REPO_ROOT, "config", "style_rules.yaml")

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

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def money_str(cost_str: str):
    try:
        v = float(cost_str)
        return f"{int(v)} gp" if v.is_integer() else f"{v:g} gp"
    except Exception:
        return None

def fmt_stats_item(fields: dict):
    cost = money_str(fields.get("cost") or "")
    weight = fields.get("weight")
    category = fields.get("category")
    stats = []
    if cost: stats.append(f"Cost: {cost}")
    if weight: stats.append(f"Weight: {weight} lb")
    if category: stats.append(f"Category: {category}")
    return " | ".join(stats) if stats else ""

def pick_voice_lines(style_cfg, voice_name, category, name):
    voices = (style_cfg.get("voices") or {})
    voice = voices.get(voice_name) or voices.get("friendly_vet") or {}

    # category-aware pools: hooks_<category>, ctas_<category>
    hk_key = f"hooks_{category}"
    ct_key = f"ctas_{category}"

    hooks = (voice.get(hk_key) or None) or (voice.get("hooks") or ["{name}."])
    ctas  = (voice.get(ct_key) or None) or (voice.get("ctas")  or ["Use it wisely."])

    # deterministic pick per voice+category+name
    h = int(hashlib.sha256(f"{voice_name}|{category}|{name}".encode("utf-8")).hexdigest(), 16)
    hook = hooks[h % len(hooks)].format(name=name)
    cta  = ctas[(h // 7) % len(ctas)]
    return hook, cta

# ---------------- Item scripts ----------------

def build_item_body(angle: str, fields: dict):
    desc = (fields.get("desc") or "").strip()
    stats = fmt_stats_item(fields)

    if angle == "story_hook":
        bits = []
        if desc: bits.append(desc)
        bits.append("In play: use it to turn one strong PC into a whole crew—hauling gates, dragging statues, or lifting a buddy out of a pit.")
        if stats: bits.append(stats)
        return " ".join(bits)

    if angle == "clever_use":
        bits = []
        if desc: bits.append(desc)
        bits.append("Clever uses: lift a portcullis just enough to squeeze under, haul a chest across a trapped hallway from cover, or rig a ‘poor man’s elevator’ in a shaft.")
        bits.append("Rule of thumb: if you can anchor it, you can move it.")
        if stats: bits.append(stats)
        return " ".join(bits)

    if angle == "drawback_watchout":
        bits = []
        if desc: bits.append(desc)
        bits.append("It needs an anchor point, time to rig, and space to work. In a cramped tunnel or mid-combat? Good luck.")
        bits.append("DM tip: ask ‘where is it anchored?’ and ‘who is holding tension?’—that’s where the tension lives.")
        if stats: bits.append(stats)
        return " ".join(bits)

    raise ValueError(f"Unsupported item angle: {angle}")

# ---------------- Monster scripts ----------------
def has_trait(traits: list, needle: str) -> bool:
    n = (needle or "").strip().lower()
    for tr in traits or []:
        if (tr.get("name") or "").strip().lower() == n:
            return True
    return False

def tactic_nugget(angle: str, traits: list) -> str:
    # Add small, grounded “expert” lines based on well-known trait mechanics.
    # Keep these short; this is Shorts content.
    if has_trait(traits, "Pack Tactics"):
        if angle == "how_it_wins":
            return "Pack Tactics means it wants adjacency—swarm one target and farm advantage."
        if angle == "common_mistake":
            return "Mistake: letting it surround you. Once it has buddies in 5 feet, the hits get sticky."
        if angle == "counterplay":
            return "Counter: break adjacency. Back up, choke the corridor, and pick them off one at a time."
    return ""


def short(s: str, n=160):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return (s[:n].rstrip() + "…") if len(s) > n else s

def sstr(v) -> str:
    # safe string for fields that might be int/float/None/list
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    return str(v)

def dedupe_prefixed_lines(lines):
    # Keeps at most one line per prefix like "Misplay:" / "DM twist:" etc.
    seen = set()
    out = []
    for s in lines:
        s = (s or "").strip()
        if not s:
            continue
        key = s.split(":", 1)[0].strip().lower() if ":" in s else s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out



def creature_anchor(fields: dict):
    # Try common fields; if missing, we just skip.
    ac = fields.get("armor_class")
    hp = fields.get("hit_points")
    spd = fields.get("speed") or fields.get("walk")  # depending on dataset
    bits = []
    if isinstance(ac, (int, float)) and ac:
        bits.append(f"AC {int(ac)}")
    if isinstance(hp, (int, float)) and hp:
        bits.append(f"HP {int(hp)}")
    if spd:
        bits.append(f"Speed {spd}")
    return " | ".join(bits)

def pick_notable_trait(traits: list):
    # prefer non-empty desc and "type" not empty
    for t in traits or []:
        if (t.get("name") or "").strip() and (t.get("desc") or "").strip():
            return t
    return (traits[0] if traits else None)

def pick_actions(actions: list, k=2):
    # prefer "attack" style or anything with a desc
    good = [a for a in (actions or []) if (a.get("name") or "").strip() and (a.get("desc") or "").strip()]
    return good[:k]

def build_monster_body(angle: str, fields: dict, traits: list, actions: list, attacks: list):
    name = fields.get("name", "This creature")
    anchor = creature_anchor(fields)
    trait = pick_notable_trait(traits)
    acts = pick_actions(actions, 2)

    trait_line = ""
    if trait:
        trait_line = f"Notable trait: {trait.get('name')}. {short(trait.get('desc'), 120)}"

    action_lines = []
    for a in acts:
        action_lines.append(f"{a.get('name')}: {short(a.get('desc'), 140)}")
    action_blob = " ".join(action_lines) if action_lines else ""

    nug = tactic_nugget(angle, traits)

    if angle == "how_it_wins":
        bits = [f"{name} wins by doing its simple job ruthlessly."]
        if anchor:
            bits.append(anchor + ".")
        if action_blob:
            bits.append("Key moves: " + action_blob)
        if trait_line:
            bits.append(trait_line)
        if nug:
            bits.append(nug)
        bits.append("Play it fast: force one bad choice, then punish it.")
        return " ".join(bits)

    if angle == "common_mistake":
        bits = [f"Common mistake vs {name}: treating it like ‘just flavor.’"]
        if anchor:
            bits.append(anchor + ".")
        if action_blob:
            bits.append("What actually hurts: " + action_blob)
        if trait_line:
            bits.append(trait_line)
        if nug:
            bits.append(nug)
        bits.append("If the party ignores positioning, this thing gets free value.")
        return " ".join(bits)

    if angle == "counterplay":
        bits = [f"Counterplay for {name}: deny its preferred fight."]
        if anchor:
            bits.append(anchor + ".")
        if action_blob:
            bits.append("Watch for: " + action_blob)
        if nug:
            bits.append(nug)
        bits.append("Use terrain, spacing, and focus-fire to remove its turns from the board.")
        if trait_line:
            bits.append("Also: " + trait_line)
        return " ".join(bits)

    raise ValueError(f"Unsupported monster angle: {angle}")


# ---------------- Spell scripts ----------------

def is_concentration(fields: dict) -> bool:
    # WotC/Open5e exports may store this as a bool, string, or embed it in duration/desc.
    v = fields.get("concentration")
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip():
        return "true" in v.strip().lower() or "concentration" in v.strip().lower()

    desc = sstr(fields.get("desc")).lower()
    dur  = sstr(fields.get("duration")).lower()
    return ("concentration" in desc) or ("concentration" in dur)
def spell_anchor(fields: dict):
    lvl = fields.get("level")
    school = fields.get("school") or fields.get("spell_school") or ""
    rng = sstr(fields.get("range"))
    dur = sstr(fields.get("duration"))
    conc = is_concentration(fields)

    # Normalize a couple common patterns
    rng_txt = rng.strip()
    if rng_txt.isdigit():
        rng_txt = f"{rng_txt} ft"
    dur_txt = dur.strip()
    if conc and "concentration" not in dur_txt.lower():
        if dur_txt:
            dur_txt = f"Concentration, up to {dur_txt}"
        else:
            dur_txt = "Concentration"

    # Level text
    if lvl is None:
        lvl_txt = ""
    else:
        try:
            il = int(lvl)
            lvl_txt = "Cantrip" if il == 0 else f"{il}th-level"
        except Exception:
            lvl_txt = str(lvl)

    parts = []
    if lvl_txt: parts.append(lvl_txt)
    if school: parts.append(str(school).title())
    if rng_txt: parts.append(f"Range: {rng_txt}")
    if dur_txt: parts.append(f"Duration: {dur_txt}")
    return " | ".join(parts)


def spell_nuggets(angle: str, fields: dict):
    nuggets = []
    rng = sstr(fields.get("range")).lower()
    dur = sstr(fields.get("duration")).lower()
    desc = sstr(fields.get("desc")).lower()

    if is_concentration(fields):
        if angle == "best_moment":
            nuggets.append("It’s Concentration—cast it when you can protect it, not when you’re about to get punched in the teeth.")
        elif angle == "common_misplay":
            nuggets.append("Misplay: dropping Concentration immediately. If you can’t keep it up, pick a different spell.")
        else:
            nuggets.append("DM twist: pressure Concentration with terrain and threats, not cheap ‘gotcha’ counters.")

        # Control-spell table advice (works for banish/maze-style effects)
        if angle == "best_moment":
            nuggets.append("Best use: swing the action economy—remove the scariest turn, then clean up.")
        elif angle == "common_misplay":
            nuggets.append("Misplay: spending a high slot to ‘delay’ a fight you could just finish.")
        else:
            nuggets.append("DM twist: have allies react—guard the exit, punish the caster, or change the objective.")
    if "touch" in rng or "melee" in rng:
        nuggets.append("Delivery matters: plan how you get into touch range without donating HP.")

    if "1 minute" in dur or "10 minutes" in dur:
        nuggets.append("Timing tip: this is often better *before* initiative than after.")

    if "saving throw" in desc or "save" in desc:
        nuggets.append("Target smart: don’t throw save-or-suck at the creature that’s built to save.")

    return nuggets[:2]

def build_spell_body(angle: str, fields: dict):
    name = fields.get("name", "This spell")
    desc = short(fields.get("desc") or "", 220)
    anchor = spell_anchor(fields)
    nugs = dedupe_prefixed_lines(spell_nuggets(angle, fields))

    if angle == "best_moment":
        bits = [f"When is {name} at its best? When it changes the situation, not just the damage math."]
        if anchor: bits.append(anchor + ".")
        if desc: bits.append(desc)
        bits += nugs
        bits.append("Ask: what problem does this solve *right now*?")
        return " ".join(bits)

    if angle == "common_misplay":
        bits = [f"Common misplay with {name}: casting it because you can, not because you should."]
        if anchor: bits.append(anchor + ".")
        if desc: bits.append(desc)
        bits += nugs
        bits.append("Better play: line it up so it forces movement, costs actions, or ends the fight faster.")
        return " ".join(bits)

    if angle == "dm_twist":
        bits = [f"DM twist for {name}: make it matter in the world, not just on the grid."]
        if anchor: bits.append(anchor + ".")
        if desc: bits.append(desc)
        bits += nugs
        bits.append("Reward clever casting with information, access, or advantage—not just a reroll.")
        return " ".join(bits)

    raise ValueError(f"Unsupported spell angle: {angle}")

def main():
    atom = load_json(ATOM_PATH)

    # Always reset script so we never show stale content if generation fails
    atom["script"] = {}

    fact = atom.get("fact") or {}
    style = atom.get("style") or {}
    category = atom.get("category")
    angle = atom.get("angle")

    if not fact:
        print("ERROR: atom.fact missing. Run: ./bin/core/attach_fact.py", file=sys.stderr)
        sys.exit(3)

    style_cfg = load_yaml(STYLE_CFG) or {}
    voice_name = style.get("voice", "friendly_vet")

    kind = fact.get("kind")
    fields = fact.get("fields") or {}
    name = fact.get("name") or fields.get("name") or "Thing"

    atom["script"] = {}
    script = atom["script"]

    if category == "item_spotlight" and kind == "item":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_item_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, cta

    elif category == "monster_tactic" and kind == "creature":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_monster_body(angle, fields, fact.get("traits") or [], fact.get("actions") or [], fact.get("attacks") or [])
        script["hook"], script["body"], script["cta"] = hook, body, cta

    elif category == "spell_use_case" and kind == "spell":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_spell_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, cta

    else:
        print(f"ERROR: Unsupported category/kind: {category}/{kind}", file=sys.stderr)
        sys.exit(4)

    full_text = f"{script.get('hook','').strip()}\n{script.get('body','').strip()}\n{script.get('cta','').strip()}\n"
    atom["script_id"] = sha256_text(full_text)

    atomic_write_json(ATOM_PATH, atom)
    print(ATOM_PATH)

if __name__ == "__main__":
    main()
