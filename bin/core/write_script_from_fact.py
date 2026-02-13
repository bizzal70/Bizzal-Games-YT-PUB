#!/usr/bin/env python3
import hashlib, json, os, sys, re
from datetime import datetime
from urllib import request, error

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


def canonical_angle(category: str, angle: str) -> str:
    a = (angle or "").strip().lower()
    c = (category or "").strip().lower()

    if c == "monster_tactic":
        return {
            "how_to_counter": "counterplay",
            "terrain_synergy": "how_it_wins",
            "party_level_scaling": "how_it_wins",
            "roleplay_hook": "common_mistake",
        }.get(a, a)

    if c == "spell_use_case":
        return {
            "combo_pairing": "best_moment",
            "upcast_tip": "best_moment",
            "dm_counterplay": "dm_twist",
        }.get(a, a)

    if c == "item_spotlight":
        return {
            "best_user": "clever_use",
            "dm_counterplay": "drawback_watchout",
        }.get(a, a)

    return a


def slugify(s: str) -> str:
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").strip().lower())
    txt = re.sub(r"-+", "-", txt).strip("-")
    return txt or "na"


def creature_context(name: str, fields: dict) -> dict:
    nm = (name or "").lower()
    ctype = sstr(fields.get("type") or fields.get("creature_type") or "").lower()
    habitat = sstr(fields.get("environment") or fields.get("habitat") or "").lower()
    speed = sstr(fields.get("speed") or fields.get("swim") or "").lower()

    aquatic_name_markers = (
        "merfolk", "sahuagin", "triton", "sea", "reef", "shark", "eel", "kraken", "water"
    )

    if "dragon" in nm or "dragon" in ctype:
        if "bronze" in nm:
            return {
                "arena": "coastline, harbor, or storm-wrecked ruins",
                "choice": "protect lives now or secure the objective before it escapes",
                "pressure": "terrain hazards and line-of-sight",
            }
        if "brass" in nm:
            return {
                "arena": "desert roads, ruins, or caravan routes",
                "choice": "take the safe route or risk a faster, costlier path",
                "pressure": "resources and conversation leverage",
            }
        return {
            "arena": "a place where mobility and range matter",
            "choice": "save people now or finish the threat fast",
            "pressure": "positioning and action economy",
        }

    if any(x in habitat for x in ("coast", "sea", "ocean", "shore", "swamp", "water")):
        return {
            "arena": "terrain with water lanes and chokepoints",
            "choice": "hold formation or split to secure objectives",
            "pressure": "movement and visibility",
        }

    if any(x in nm for x in aquatic_name_markers) or "swim" in speed:
        return {
            "arena": "flooded lanes, docks, or half-submerged ruins",
            "choice": "hold dry ground or overextend to secure the objective",
            "pressure": "mobility and line control",
        }

    return {
        "arena": "terrain with one strong feature",
        "choice": "save resources now or spend big to control tempo",
        "pressure": "positioning and objective pressure",
    }


def build_contextual_cta(category: str, angle: str, kind: str, name: str, fields: dict, default_cta: str) -> str:
    c = canonical_category(category)
    a = canonical_angle(c, angle)
    fallback = (default_cta or "DMs: run it with intent and reward smart play.").strip()

    if c == "encounter_seed" and kind == "creature":
        ctx = creature_context(name, fields)
        if a == "moral_choice":
            return f"DMs: stage it in {ctx['arena']} and force this choice by round 2: {ctx['choice']}."
        if a == "time_pressure":
            return f"DMs: put a visible countdown on the table; every lost round should escalate {ctx['pressure']}."
        if a == "terrain_feature":
            return "DMs: pick one map feature as the win condition; if they ignore it, they lose tempo immediately."
        if a == "twist":
            return "DMs: flip the objective at midpoint and make the first plan insufficient without punishing creativity."
        return "DMs: telegraph stakes in the first beat, then make the cost of delay obvious."

    if c == "monster_tactic" and kind == "creature":
        if a == "counterplay":
            return "Players: deny its preferred fight shape first, then focus fire." 
        if a == "common_mistake":
            return "DMs: punish lazy positioning once, then let the table adapt."
        return "DMs: run its game plan on purpose; players, answer with movement and target priority."

    if c == "spell_use_case" and kind == "spell":
        if a == "best_moment":
            return "Players: cast when it changes the objective, not when it only adds numbers."
        if a == "common_misplay":
            return "Table tip: call timing and target before you spend the slot."
        if a == "dm_twist":
            return "DMs: reward smart casting with meaningful scene consequences."
        return "Use spell timing as a decision tool, not just a damage button."

    if c == "item_spotlight" and kind == "item":
        if a == "story_hook":
            return "DMs: tie the item to a concrete objective so utility beats raw DPR."
        if a == "drawback_watchout":
            return "Players: declare setup and anchor points before the roll."
        return "Players: prep the environment first, then let the item do work."

    if c in ("rules_ruling", "rules_myth"):
        return "Table rule: make one clear call, apply it consistently, and move on."

    if c == "character_micro_tip":
        return "Pick one repeatable decision pattern and run it every session until it is automatic."

    return fallback


def env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def maybe_ai_polish_cta(atom: dict, fact: dict, style: dict, script: dict) -> str:
    current_cta = (script.get("cta") or "").strip()
    if not current_cta:
        return current_cta

    if not env_true("BIZZAL_ENABLE_AI", False):
        return current_cta

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BIZZAL_OPENAI_API_KEY")
    if not api_key:
        return current_cta

    model = os.getenv("BIZZAL_OPENAI_MODEL", "gpt-4o-mini")
    endpoint = os.getenv("BIZZAL_OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions")

    category = atom.get("category") or ""
    angle = atom.get("angle") or ""
    name = fact.get("name") or (fact.get("fields") or {}).get("name") or "This"
    voice = style.get("voice") or "friendly_vet"
    kind = fact.get("kind") or "unknown"

    prefix = "DMs"
    m = re.match(r"^\s*([A-Za-z ]{2,20}):", current_cta)
    if m:
        maybe_prefix = m.group(1).strip()
        if maybe_prefix:
            prefix = maybe_prefix

    prompt = {
        "category": category,
        "angle": angle,
        "kind": kind,
        "fact_name": name,
        "voice": voice,
        "hook": script.get("hook", ""),
        "body": script.get("body", ""),
        "current_cta": current_cta,
        "requirements": [
            "Return exactly one CTA sentence.",
            f"Start with '{prefix}:'.",
            "Match the hook/body tactical intent and creature/spell/item context.",
            "Avoid generic phrasing like 'drop one in the dungeon'.",
            "Keep it concise: 12-24 words.",
            "No markdown, no bullets, no quotes.",
        ],
    }

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "You rewrite RPG short-form CTA lines to be natural, specific, and aligned with tactical context.",
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
    }

    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        candidate = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        candidate = clean_script_text(candidate)
        candidate = short(candidate, 180, add_ellipsis=False)

        if not candidate:
            return current_cta

        if not re.match(r"^[A-Za-z ]{2,20}:", candidate):
            candidate = f"{prefix}: {candidate}"

        if len(candidate.split()) < 5:
            return current_cta

        return candidate
    except Exception as exc:
        if env_true("DEBUG_RENDER", False):
            print(f"[write_script_from_fact] AI CTA polish skipped: {exc}", file=sys.stderr)
        return current_cta


def locked_tokens(script: dict, fact: dict) -> list:
    tokens = set()
    name = (fact.get("name") or (fact.get("fields") or {}).get("name") or "").strip()
    if name:
        tokens.add(name)

    for text in [script.get("hook", ""), script.get("body", ""), script.get("cta", "")]:
        for n in re.findall(r"\b\d+(?:\.\d+)?\b", text or ""):
            tokens.add(n)
    return sorted(tokens)


def maybe_ai_polish_script(atom: dict, fact: dict, style: dict, script: dict) -> dict:
    if not env_true("BIZZAL_ENABLE_AI_SCRIPT", False):
        return script

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BIZZAL_OPENAI_API_KEY")
    if not api_key:
        return script

    model = os.getenv("BIZZAL_OPENAI_MODEL", "gpt-4o-mini")
    endpoint = os.getenv("BIZZAL_OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions")

    prompt = {
        "task": "Rewrite hook/body/cta to sound more personal while preserving factual integrity.",
        "category": atom.get("category") or "",
        "angle": atom.get("angle") or "",
        "fact_name": fact.get("name") or (fact.get("fields") or {}).get("name") or "",
        "kind": fact.get("kind") or "",
        "voice": style.get("voice") or "friendly_vet",
        "persona": style.get("persona") or "table_coach",
        "tone": style.get("tone") or "neutral",
        "locked_tokens": locked_tokens(script, fact),
        "input": {
            "hook": script.get("hook", ""),
            "body": script.get("body", ""),
            "cta": script.get("cta", ""),
        },
        "rules": [
            "Return strict JSON object with keys: hook, body, cta.",
            "Do not invent new stats, rules, or proper nouns.",
            "Keep all numeric facts and fact_name intact.",
            "Hook: one sentence. Body: 2-4 sentences. CTA: one sentence.",
            "No markdown.",
        ],
    }

    payload = {
        "model": model,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are an RPG script editor improving tone while preserving factual correctness.",
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
    }

    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=35) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}")
        obj = json.loads(content)

        out = {
            "hook": clean_script_text(obj.get("hook") or script.get("hook", "")),
            "body": clean_script_text(obj.get("body") or script.get("body", "")),
            "cta": clean_script_text(obj.get("cta") or script.get("cta", "")),
        }

        blob = f"{out['hook']} {out['body']} {out['cta']}"
        for token in locked_tokens(script, fact):
            if token and token not in blob:
                return script

        if not out["hook"] or not out["body"] or not out["cta"]:
            return script

        return out
    except Exception as exc:
        if env_true("DEBUG_RENDER", False):
            print(f"[write_script_from_fact] AI script polish skipped: {exc}", file=sys.stderr)
        return script


def build_content_contract(atom: dict, script_id: str, script: dict, fact: dict, style: dict):
    day = atom.get("day") or datetime.now().strftime("%Y-%m-%d")
    month_id = day[:7]
    category = slugify(atom.get("category") or "")
    angle = slugify(atom.get("angle") or "")
    voice = slugify(style.get("voice") or "friendly_vet")
    tone = slugify(style.get("tone") or "neutral")

    kind = slugify(fact.get("kind") or "unknown")
    fact_pk = slugify(str(fact.get("pk") or fact.get("name") or "unknown"))
    canonical_base = f"{day}-{category}-{kind}-{fact_pk}"
    canonical_hash = sha256_text(canonical_base + "|" + script_id)
    short_hash = canonical_hash[:12]

    content_id = f"bgp-{canonical_base}-{short_hash}"
    episode_id = f"ep-{day}-{category}-{short_hash}"
    month_bundle_id = f"zine-{month_id}-{sha256_text(month_id)[:8]}"

    segments = {}
    for key in ("hook", "body", "cta"):
        segment_id = f"seg-{key}-{sha256_text(content_id + '|' + key)[:10]}"
        voice_track_id = f"vox-{key}-{sha256_text(segment_id + '|voice')[:10]}"
        visual_asset_id = f"img-{key}-{sha256_text(segment_id + '|visual')[:10]}"
        segments[key] = {
            "segment_id": segment_id,
            "order": {"hook": 1, "body": 2, "cta": 3}[key],
            "text": script.get(key, ""),
            "voice_track_id": voice_track_id,
            "visual_asset_id": visual_asset_id,
        }

    tags = sorted({
        "content_press",
        "shorts",
        month_id,
        category,
        angle,
        kind,
        voice,
        tone,
        slugify(str(fact.get("document") or "")),
    })

    voiceover = style.get("voiceover") or {}

    return {
        "content_id": content_id,
        "episode_id": episode_id,
        "month_id": month_id,
        "month_bundle_id": month_bundle_id,
        "canonical_hash": canonical_hash,
        "script_id": script_id,
        "asset_contract": {
            "voice_pack_id": voiceover.get("voice_pack_id") or f"voice-{voice}",
            "tts_voice_id": voiceover.get("tts_voice_id") or "alloy",
            "visual_pack_id": f"visual-{category}",
            "timeline_id": f"timeline-{sha256_text(content_id + '|timeline')[:10]}",
        },
        "segments": segments,
        "tags": tags,
    }

# ---------------- Item scripts ----------------

def build_item_body(angle: str, fields: dict):
    angle = {
        "best_user": "clever_use",
        "dm_counterplay": "drawback_watchout",
    }.get((angle or "").strip().lower(), (angle or "").strip().lower())

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

    bits = []
    if desc: bits.append(desc)
    if stats: bits.append(stats)
    bits.append("Use this when the party can solve positioning before they solve damage.")
    return " ".join(bits)

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


def short(s: str, n=160, add_ellipsis=True):
    s = re.sub(r"\s+", " ", (s or "").strip())
    if len(s) <= n:
        return s

    window = s[: n + 1]

    # Prefer ending on a full thought when possible.
    sentence_break = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence_break >= int(n * 0.6):
        return window[: sentence_break + 1].strip()

    clause_break = max(window.rfind("; "), window.rfind(": "), window.rfind(", "))
    if clause_break >= int(n * 0.7):
        out = window[:clause_break].strip().rstrip(",;:")
        return (out + "…") if add_ellipsis else (out + ".")

    cut = window.rfind(" ")
    if cut <= 0:
        cut = n

    trimmed = window[:cut].strip().rstrip(",;:-")
    trailing_words = r"(of|and|or|to|with|for|at|in|on|by|from|the|a|an|is|are|was|were|be)"
    while True:
        updated = re.sub(rf"\b{trailing_words}$", "", trimmed, flags=re.IGNORECASE).rstrip()
        if updated == trimmed:
            break
        trimmed = updated
    if trimmed:
        return (trimmed + "…") if add_ellipsis else (trimmed + ".")
    fallback = s[:n].rstrip().rstrip(",;:-")
    return (fallback + "…") if add_ellipsis else (fallback + ".")

def clean_script_text(s: str) -> str:
    txt = re.sub(r"\s+", " ", (s or "").strip())
    if not txt:
        return ""

    txt = txt.replace("…", ".")
    txt = txt.replace("*", "")
    txt = re.sub(r"\s+([,.;:!?])", r"\1", txt)
    txt = re.sub(r"([,.;:!?])([^\s])", r"\1 \2", txt)
    txt = re.sub(r"\.{2,}", ".", txt)
    txt = re.sub(r"\s+", " ", txt).strip()

    if txt and txt[-1] not in ".!?":
        txt += "."

    return txt

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
    angle = {
        "how_to_counter": "counterplay",
        "terrain_synergy": "how_it_wins",
        "party_level_scaling": "how_it_wins",
        "roleplay_hook": "common_mistake",
    }.get((angle or "").strip().lower(), (angle or "").strip().lower())

    name = fields.get("name", "This creature")
    anchor = creature_anchor(fields)
    trait = pick_notable_trait(traits)
    acts = pick_actions(actions, 2)

    trait_line = ""
    if trait:
        trait_line = f"Notable trait: {trait.get('name')}. {short(trait.get('desc'), 120, add_ellipsis=False)}"

    action_names = [a.get("name") for a in acts if (a.get("name") or "").strip()]
    action_blob = ", ".join(action_names) if action_names else ""

    nug = tactic_nugget(angle, traits)

    if angle == "how_it_wins":
        bits = [f"{name} wins by doing its simple job ruthlessly."]
        if anchor:
            bits.append(anchor + ".")
        if action_blob:
            bits.append("Key moves: " + action_blob + ".")
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
            bits.append("What actually hurts: " + action_blob + ".")
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
            bits.append("Watch for: " + action_blob + ".")
        if nug:
            bits.append(nug)
        bits.append("Use terrain, spacing, and focus-fire to remove its turns from the board.")
        if trait_line:
            bits.append("Also: " + trait_line)
        return " ".join(bits)

    bits = [f"{name} is dangerous when it gets its preferred position."]
    if anchor:
        bits.append(anchor + ".")
    if trait_line:
        bits.append(trait_line)
    if action_blob:
        bits.append("Watch for: " + action_blob + ".")
    bits.append("Run it with intent and force the table to answer its pressure.")
    return " ".join(bits)


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
            if dur_txt.lower().startswith("up to "):
                dur_txt = f"Concentration, {dur_txt}"
            else:
                dur_txt = f"Concentration, up to {dur_txt}"
        else:
            dur_txt = "Concentration"

    # Level text
    if lvl is None:
        lvl_txt = ""
    else:
        try:
            il = int(lvl)
            if il == 0:
                lvl_txt = "Cantrip"
            else:
                suffix = "th"
                if il % 100 not in (11, 12, 13):
                    if il % 10 == 1:
                        suffix = "st"
                    elif il % 10 == 2:
                        suffix = "nd"
                    elif il % 10 == 3:
                        suffix = "rd"
                lvl_txt = f"{il}{suffix}-level"
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
    angle = {
        "combo_pairing": "best_moment",
        "upcast_tip": "best_moment",
        "dm_counterplay": "dm_twist",
    }.get((angle or "").strip().lower(), (angle or "").strip().lower())

    name = fields.get("name", "This spell")
    desc = short(fields.get("desc") or "", 220, add_ellipsis=False)
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

    bits = [f"{name} is strongest when cast to change the encounter state, not just to roll damage."]
    if anchor: bits.append(anchor + ".")
    if desc: bits.append(desc)
    bits += nugs
    bits.append("Choose timing and target first, then spend the slot.")
    return " ".join(bits)

def build_rule_body(angle: str, fields: dict):
    name = fields.get("name") or "Rule"
    desc = short(fields.get("desc") or fields.get("text") or fields.get("content") or "", 220, add_ellipsis=False)
    angle = (angle or "").strip().lower()

    if angle == "common_table_mistake":
        lead = f"Common table mistake around {name}: speed over clarity."
    elif angle == "fast_ruling":
        lead = f"Fast ruling for {name}: decide intent, then resolve with one clear call."
    elif angle == "edge_case":
        lead = f"Edge case for {name}: check order of operations before adjudicating."
    elif angle == "dm_fairness_tip":
        lead = f"DM fairness tip with {name}: be consistent across allies and enemies."
    elif angle == "player_tip":
        lead = f"Player tip for {name}: state your plan and timing before rolling."
    elif angle == "myth_vs_rule":
        lead = f"Myth vs rule: {name}."
    elif angle == "why_people_get_it_wrong":
        lead = f"Why people get {name} wrong: shorthand becomes house rule over time."
    elif angle == "quick_example":
        lead = f"Quick example for {name}: call the trigger, then apply the effect once."
    elif angle == "dm_callout":
        lead = f"DM callout on {name}: telegraph the ruling once, then stick to it."
    else:
        lead = f"Rules note: {name}."

    bits = [lead]
    if desc:
        bits.append(desc)
    bits.append("Clear rulings now save argument time later.")
    return " ".join(bits)

def build_class_body(angle: str, fields: dict):
    name = fields.get("name") or "This class"
    desc = short(fields.get("desc") or fields.get("description") or "", 220, add_ellipsis=False)
    angle = (angle or "").strip().lower()

    if angle == "level_1_choice":
        lead = f"Level 1 choice for {name}: pick a play pattern you can execute every fight."
    elif angle == "party_role":
        lead = f"Party role for {name}: define what you solve before initiative starts."
    elif angle == "survivability":
        lead = f"Survivability with {name}: position first, then pressure."
    elif angle == "exploration_edge":
        lead = f"Exploration edge for {name}: look for non-combat value every scene."
    elif angle == "table_etiquette":
        lead = f"Table tip for {name}: declare intent early so teammates can combo around you."
    else:
        lead = f"Character tip: {name}."

    bits = [lead]
    if desc:
        bits.append(desc)
    bits.append("Strong turns come from repeatable decisions, not lucky spikes.")
    return " ".join(bits)

def build_encounter_body(angle: str, fields: dict, traits: list, actions: list):
    name = fields.get("name") or "This encounter anchor"
    anchor = creature_anchor(fields)
    angle = (angle or "").strip().lower()

    if angle == "three_beats":
        lead = f"Three-beat encounter seed: reveal {name}, escalate pressure, then force a hard choice."
    elif angle == "twist":
        lead = f"Twist for a {name} encounter: change the objective mid-scene, not just the hit points."
    elif angle == "terrain_feature":
        lead = f"Terrain feature seed with {name}: make the map itself a problem to solve."
    elif angle == "time_pressure":
        lead = f"Time pressure seed for {name}: each round lost should cost position, resources, or civilians."
    elif angle == "moral_choice":
        lead = f"Moral-choice seed with {name}: success should ask what the party is willing to sacrifice."
    else:
        lead = f"Encounter seed using {name}: set stakes before the first roll."

    bits = [lead]
    if anchor:
        bits.append(anchor + ".")
    nug = tactic_nugget("how_it_wins", traits)
    if nug:
        bits.append(nug)
    if actions:
        action_names = [a.get("name") for a in actions if (a.get("name") or "").strip()]
        if action_names:
            bits.append("Signature pressure: " + ", ".join(action_names[:2]) + ".")
    bits.append("Give players one clear clue and one costly decision.")
    return " ".join(bits)

def main():
    atom = load_json(ATOM_PATH)

    # Always reset script so we never show stale content if generation fails
    atom["script"] = {}

    fact = atom.get("fact") or {}
    style = atom.get("style") or {}
    category = canonical_category(atom.get("category"))
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
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta)

    elif category == "monster_tactic" and kind == "creature":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_monster_body(angle, fields, fact.get("traits") or [], fact.get("actions") or [], fact.get("attacks") or [])
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta)

    elif category == "spell_use_case" and kind == "spell":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_spell_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta)

    elif category == "encounter_seed" and kind == "creature":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_encounter_body(angle, fields, fact.get("traits") or [], fact.get("actions") or [])
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta)

    elif category in ("rules_ruling", "rules_myth") and kind == "rule":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_rule_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta)

    elif category == "character_micro_tip" and kind == "class":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name)
        body = build_class_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta)

    else:
        print(f"ERROR: Unsupported category/kind: {category}/{kind}", file=sys.stderr)
        sys.exit(4)

    for key in ("hook", "body", "cta"):
        script[key] = clean_script_text(script.get(key, ""))

    script = maybe_ai_polish_script(atom, fact, style, script)
    atom["script"] = script

    script["cta"] = maybe_ai_polish_cta(atom, fact, style, script)
    script["cta"] = clean_script_text(script.get("cta", ""))

    full_text = f"{script.get('hook','').strip()}\n{script.get('body','').strip()}\n{script.get('cta','').strip()}\n"
    atom["script_id"] = sha256_text(full_text)
    atom["content"] = build_content_contract(atom, atom["script_id"], script, fact, style)

    atomic_write_json(ATOM_PATH, atom)
    print(ATOM_PATH)

if __name__ == "__main__":
    main()
