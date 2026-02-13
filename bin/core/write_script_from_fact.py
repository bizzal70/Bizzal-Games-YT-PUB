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

def pick_voice_lines(style_cfg, voice_name, category, name, angle="", day=""):
    voices = (style_cfg.get("voices") or {})
    voice = voices.get(voice_name) or voices.get("friendly_vet") or {}

    # category-aware pools: hooks_<category>, ctas_<category>
    hk_key = f"hooks_{category}"
    ct_key = f"ctas_{category}"

    hooks = (voice.get(hk_key) or None) or (voice.get("hooks") or ["{name}."])
    ctas  = (voice.get(ct_key) or None) or (voice.get("ctas")  or ["Use it wisely."])

    # deterministic pick per day+voice+category+angle+name (varies across days/topics)
    h = int(hashlib.sha256(f"{day}|{voice_name}|{category}|{angle}|{name}".encode("utf-8")).hexdigest(), 16)
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


def build_contextual_cta(category: str, angle: str, kind: str, name: str, fields: dict, default_cta: str, day: str = "") -> str:
    c = canonical_category(category)
    a = canonical_angle(c, angle)
    fallback = (default_cta or "DMs: run it with intent and reward smart play.").strip()

    if c == "encounter_seed" and kind == "creature":
        ctx = creature_context(name, fields)
        if a == "moral_choice":
            return deterministic_pick([
                f"DMs: by round 2, force this call—protect people now or finish the objective before the cost spikes.",
                f"DMs: make the table choose fast: secure the objective, or spend turns protecting who gets caught in the fallout.",
                f"DMs: present two valid wins, then require a sacrifice—save everyone or end the threat quickly, not both.",
            ], f"cta|{day}|{c}|{a}|{name}")
        if a == "time_pressure":
            return deterministic_pick([
                f"DMs: put a visible countdown on the table; every lost round should escalate {ctx['pressure']}.",
                f"DMs: show the timer up front, then make delay increase {ctx['pressure']} each round.",
                f"DMs: make the clock explicit and charge interest every turn through {ctx['pressure']}.",
            ], f"cta|{day}|{c}|{a}|{name}")
        if a == "terrain_feature":
            return deterministic_pick([
                "DMs: pick one map feature as the win condition; if they ignore it, they lose tempo immediately.",
                "DMs: make one terrain control point decide the flow of the fight.",
                "DMs: tie success to one terrain feature the party must contest early.",
            ], f"cta|{day}|{c}|{a}|{name}")
        if a == "twist":
            return deterministic_pick([
                "DMs: flip the objective at midpoint and make the first plan insufficient without punishing creativity.",
                "DMs: pivot the win condition once they commit, then reward adaptation.",
                "DMs: spring a midpoint objective shift that changes priorities, not just difficulty.",
            ], f"cta|{day}|{c}|{a}|{name}")
        return deterministic_pick([
            "DMs: telegraph stakes in the first beat, then make the cost of delay obvious.",
            "DMs: show consequence first, then force commitment.",
            "DMs: put stakes on screen early so every choice has weight.",
        ], f"cta|{day}|{c}|{a}|{name}")

    if c == "monster_tactic" and kind == "creature":
        if a == "counterplay":
            return deterministic_pick([
                "Players: deny its preferred fight shape first, then focus fire.",
                "Players: break its setup turn, then collapse one target together.",
                "Players: win position first; damage second.",
            ], f"cta|{day}|{c}|{a}|{name}")
        if a == "common_mistake":
            return deterministic_pick([
                "DMs: punish lazy positioning once, then let the table adapt.",
                "DMs: let one positional mistake hurt so the lesson sticks.",
                "DMs: enforce one clear consequence, then reward cleaner play.",
            ], f"cta|{day}|{c}|{a}|{name}")
        return deterministic_pick([
            "DMs: run its game plan on purpose; players, answer with movement and target priority.",
            "Run the statblock like a plan, then make the table solve it.",
            "Treat it like a tactical puzzle, not a sack of hit points.",
        ], f"cta|{day}|{c}|{a}|{name}")

    if c == "spell_use_case" and kind == "spell":
        if a == "best_moment":
            return deterministic_pick([
                "Players: cast when it changes the objective, not when it only adds numbers.",
                "Players: spend the slot when it flips tempo, not just when damage looks pretty.",
                "Players: treat this as a scene tool first and a damage tool second.",
            ], f"cta|{day}|{c}|{a}|{name}")
        if a == "common_misplay":
            return deterministic_pick([
                "Table tip: call timing and target before you spend the slot.",
                "Call your target and intent first; casting gets cleaner fast.",
                "Declare the plan before the spell so the table can play around it.",
            ], f"cta|{day}|{c}|{a}|{name}")
        if a == "dm_twist":
            return deterministic_pick([
                "DMs: reward smart casting with meaningful scene consequences.",
                "DMs: let clever spell use change stakes, not just hit points.",
                "DMs: pay off good casting choices with tactical or narrative advantage.",
            ], f"cta|{day}|{c}|{a}|{name}")
        return deterministic_pick([
            "Use spell timing as a decision tool, not just a damage button.",
            "Make timing your first decision; damage is the second.",
            "Pick the moment first, then pick the slot.",
        ], f"cta|{day}|{c}|{a}|{name}")

    if c == "item_spotlight" and kind == "item":
        if a == "story_hook":
            return deterministic_pick([
                "DMs: tie the item to a concrete objective so utility beats raw DPR.",
                "DMs: make this item matter by attaching it to a mission-critical obstacle.",
                "DMs: put this tool between the party and progress, not just treasure.",
            ], f"cta|{day}|{c}|{a}|{name}")
        if a == "drawback_watchout":
            return deterministic_pick([
                "Players: declare setup and anchor points before the roll.",
                "Players: call your setup details first so the item can actually shine.",
                "Players: solve placement before outcome.",
            ], f"cta|{day}|{c}|{a}|{name}")
        return deterministic_pick([
            "Players: prep the environment first, then let the item do work.",
            "Players: use positioning to make this item worth more than raw damage.",
            "Players: set the scene, then cash in the tool.",
        ], f"cta|{day}|{c}|{a}|{name}")

    if c in ("rules_ruling", "rules_myth"):
        return deterministic_pick([
            "Table rule: make one clear call, apply it consistently, and move on.",
            "Rule flow: decide once, explain briefly, keep the game moving.",
            "Consistency beats complexity—pick the ruling and stick to it.",
        ], f"cta|{day}|{c}|{a}|{name}")

    if c == "character_micro_tip":
        return deterministic_pick([
            "Pick one repeatable decision pattern and run it every session until it is automatic.",
            "Choose one class habit and execute it every fight until it becomes muscle memory.",
            "Build consistency first; big highlight turns will follow.",
        ], f"cta|{day}|{c}|{a}|{name}")

    return fallback


def env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def split_sentences(text: str) -> list:
    txt = re.sub(r"\s+", " ", (text or "").strip())
    if not txt:
        return []
    parts = re.split(r"(?<=[.!?])\s+", txt)
    return [p.strip() for p in parts if p.strip()]


def pdf_flavor_required() -> bool:
    return env_true("BIZZAL_REQUIRE_PDF_FLAVOR", False)


def pdf_flavor_keywords(snippet: str, fact_name: str) -> set:
    txt = (snippet or "").lower()
    name_tokens = set(re.findall(r"[a-z]{3,}", (fact_name or "").lower()))
    stop = {
        "the", "and", "with", "from", "that", "this", "when", "your", "into", "have", "will",
        "they", "their", "them", "than", "then", "where", "which", "while", "about", "after",
        "before", "under", "over", "against", "within", "without", "each", "other", "during",
        "creature", "target", "spell", "item", "class", "monster", "damage", "attack", "action",
        "minute", "round", "feet", "foot", "level", "range", "duration", "concentration",
    }
    words = set(re.findall(r"[a-z]{5,}", txt))
    return {w for w in words if w not in stop and w not in name_tokens}


def ai_references_pdf_flavor(text: str, snippet: str, fact_name: str) -> bool:
    if not snippet:
        return True
    keys = pdf_flavor_keywords(snippet, fact_name)
    if not keys:
        return True
    low = (text or "").lower()
    return any(k in low for k in keys)


def maybe_pdf_flavor_snippet(atom: dict, fact: dict) -> str:
    if not env_true("BIZZAL_ENABLE_PDF_FLAVOR", False):
        ai_diag("PDF flavor disabled (BIZZAL_ENABLE_PDF_FLAVOR=0)")
        return ""

    source = atom.get("source") or {}
    pdf_path = source.get("srd_pdf_path") or os.getenv("BIZZAL_SRD_PDF_PATH") or os.getenv("BG_SRD_PDF_PATH")
    if not pdf_path or not os.path.exists(pdf_path):
        ai_diag(f"PDF flavor unavailable: missing path '{pdf_path or ''}'")
        return ""

    name = (fact.get("name") or (fact.get("fields") or {}).get("name") or "").strip()
    if not name:
        ai_diag("PDF flavor skipped: missing fact name")
        return ""

    try:
        from pypdf import PdfReader  # optional dependency
    except Exception:
        ai_diag("PDF flavor unavailable: missing pypdf dependency")
        return ""

    needle = name.lower()
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages[:220]:
            txt = (page.extract_text() or "").strip()
            if not txt:
                continue
            low = txt.lower()
            idx = low.find(needle)
            if idx < 0:
                continue

            start = max(0, idx - 320)
            end = min(len(txt), idx + 520)
            window = txt[start:end]
            sents = split_sentences(window)
            for s in sents:
                if needle in s.lower():
                    ai_diag(f"PDF flavor snippet used for '{name}'")
                    return short(clean_script_text(s), 180, add_ellipsis=False)
            if sents:
                ai_diag(f"PDF flavor snippet used for '{name}'")
                return short(clean_script_text(sents[0]), 180, add_ellipsis=False)
            ai_diag(f"PDF flavor snippet used for '{name}'")
            return short(clean_script_text(window), 180, add_ellipsis=False)
    except Exception:
        ai_diag("PDF flavor lookup failed during PDF parsing")
        return ""

    ai_diag(f"PDF flavor snippet not found for '{name}'")
    return ""


def maybe_ai_polish_cta(atom: dict, fact: dict, style: dict, script: dict) -> str:
    current_cta = (script.get("cta") or "").strip()
    if not current_cta:
        return current_cta

    if not env_true("BIZZAL_ENABLE_AI", False):
        ai_diag("AI CTA polish off (BIZZAL_ENABLE_AI=0)")
        return current_cta

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BIZZAL_OPENAI_API_KEY")
    if not api_key:
        ai_diag("AI CTA polish disabled: missing OPENAI_API_KEY")
        return current_cta

    if looks_like_placeholder_key(api_key):
        ai_diag("AI CTA polish disabled: placeholder API key detected")
        return current_cta

    model = os.getenv("BIZZAL_OPENAI_MODEL", "gpt-4o-mini")
    endpoint = os.getenv("BIZZAL_OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions")

    category = atom.get("category") or ""
    angle = atom.get("angle") or ""
    name = fact.get("name") or (fact.get("fields") or {}).get("name") or "This"
    voice = style.get("voice") or "friendly_vet"
    kind = fact.get("kind") or "unknown"
    pdf_snippet = maybe_pdf_flavor_snippet(atom, fact)

    if pdf_flavor_required() and not pdf_snippet:
        ai_diag("AI CTA polish skipped: PDF flavor required but no snippet found")
        return current_cta
    if not pdf_flavor_required() and not pdf_snippet:
        ai_diag("AI CTA polish continuing without PDF flavor snippet (best-effort mode)")

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
        "persona": style.get("persona") or "table_coach",
        "tone": style.get("tone") or "neutral",
        "pdf_flavor_snippet": pdf_snippet,
        "hook": script.get("hook", ""),
        "body": script.get("body", ""),
        "current_cta": current_cta,
        "requirements": [
            "Return exactly one CTA sentence.",
            f"Start with '{prefix}:'.",
            "Match the hook/body tactical intent and creature/spell/item context.",
            "Avoid generic phrasing like 'drop one in the dungeon'.",
            "Use practical table-facing language, not theatrical narration.",
            "Keep it concise: 12-24 words.",
            "Avoid phrases like 'create a tense environment' and 'challenge players to decide'.",
            "When pdf_flavor_snippet is provided, include at least one concrete detail from it.",
            "No markdown, no bullets, no quotes.",
        ],
    }

    if canonical_category(category) == "encounter_seed" and (angle or "").strip().lower() == "moral_choice":
        prompt["requirements"].append("Moral-choice CTA must express a protect-vs-objective tradeoff.")
        prompt["requirements"].append("Do not mention terrain features or map-control phrasing.")

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
        candidate = clean_ai_style_text(candidate, segment="cta")
        candidate = short(candidate, 180, add_ellipsis=False)

        if not candidate:
            ai_diag("AI CTA polish returned empty; kept deterministic CTA")
            return current_cta

        if not re.match(r"^[A-Za-z ]{2,20}:", candidate):
            candidate = f"{prefix}: {candidate}"

        if len(candidate.split()) < 5:
            ai_diag("AI CTA polish too short; kept deterministic CTA")
            return current_cta

        if pdf_snippet and not ai_references_pdf_flavor(candidate, pdf_snippet, name):
            ai_diag("AI CTA polish rejected: missing PDF flavor grounding")
            return current_cta

        if candidate != current_cta:
            ai_diag("AI CTA polish applied")
        else:
            ai_diag("AI CTA polish produced equivalent CTA")
        return candidate
    except Exception as exc:
        ai_diag(f"AI CTA polish skipped: {exc}")
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
        ai_diag("AI script polish off (BIZZAL_ENABLE_AI_SCRIPT=0)")
        return script

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BIZZAL_OPENAI_API_KEY")
    if not api_key:
        ai_diag("AI script polish disabled: missing OPENAI_API_KEY")
        return script

    if looks_like_placeholder_key(api_key):
        ai_diag("AI script polish disabled: placeholder API key detected")
        return script

    model = os.getenv("BIZZAL_OPENAI_MODEL", "gpt-4o-mini")
    endpoint = os.getenv("BIZZAL_OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions")
    fact_name = fact.get("name") or (fact.get("fields") or {}).get("name") or ""
    pdf_snippet = maybe_pdf_flavor_snippet(atom, fact)

    if pdf_flavor_required() and not pdf_snippet:
        ai_diag("AI script polish skipped: PDF flavor required but no snippet found")
        return script
    if not pdf_flavor_required() and not pdf_snippet:
        ai_diag("AI script polish continuing without PDF flavor snippet (best-effort mode)")

    prompt = {
        "task": "Rewrite hook/body/cta to sound more personal while preserving factual integrity.",
        "category": atom.get("category") or "",
        "angle": atom.get("angle") or "",
        "fact_name": fact_name,
        "kind": fact.get("kind") or "",
        "voice": style.get("voice") or "friendly_vet",
        "persona": style.get("persona") or "table_coach",
        "tone": style.get("tone") or "neutral",
        "pdf_flavor_snippet": pdf_snippet,
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
            "Prefer concise DM coaching language over theatrical fantasy narration.",
            "Avoid generic opening phrases like 'Explore the moral dilemma' or 'Shine a light on'.",
            "Avoid soft filler like 'in your next session'.",
            "Make language concrete and table-actionable.",
            "When pdf_flavor_snippet is provided, include at least one concrete detail from it.",
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
            "hook": clean_ai_style_text(obj.get("hook") or script.get("hook", ""), segment="hook"),
            "body": clean_ai_style_text(obj.get("body") or script.get("body", ""), segment="body"),
            "cta": clean_ai_style_text(obj.get("cta") or script.get("cta", ""), segment="cta"),
        }

        if is_generic_hook(out.get("hook", "")):
            out["hook"] = clean_ai_style_text(script.get("hook", ""), segment="hook")
            ai_diag("AI script hook reverted by anti-generic gate")
        if is_generic_cta(out.get("cta", "")):
            out["cta"] = clean_ai_style_text(script.get("cta", ""), segment="cta")
            ai_diag("AI script CTA reverted by anti-generic gate")

        blob = f"{out['hook']} {out['body']} {out['cta']}"
        for token in locked_tokens(script, fact):
            if token and token not in blob:
                ai_diag(f"AI script polish rejected: missing locked token '{token}'")
                return script

        if not out["hook"] or not out["body"] or not out["cta"]:
            ai_diag("AI script polish rejected: blank segment")
            return script

        if pdf_snippet and not ai_references_pdf_flavor(blob, pdf_snippet, fact_name):
            ai_diag("AI script polish rejected: missing PDF flavor grounding")
            return script

        changed = (out.get("hook") != script.get("hook") or out.get("body") != script.get("body") or out.get("cta") != script.get("cta"))
        if changed:
            ai_diag("AI script polish applied")
        else:
            ai_diag("AI script polish produced equivalent script")

        return out
    except Exception as exc:
        ai_diag(f"AI script polish skipped: {exc}")
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


def deterministic_pick(options, seed_key: str):
    opts = [o for o in (options or []) if str(o).strip()]
    if not opts:
        return ""
    h = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest(), 16)
    return opts[h % len(opts)]


def ai_diag_enabled() -> bool:
    return env_true("DEBUG_RENDER", False) or env_true("BIZZAL_AI_DIAG", False)


def looks_like_placeholder_key(api_key: str) -> bool:
    k = (api_key or "").strip()
    if not k:
        return True
    markers = ["YOUR_OPENAI_API_KEY", "REPLACE_ME", "PASTE", "sk-xxxxx"]
    upper = k.upper()
    return any(m in upper for m in markers)


def ai_diag(msg: str):
    if ai_diag_enabled():
        print(f"[write_script_from_fact] {msg}", file=sys.stderr)

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


def clean_ai_style_text(s: str, segment: str = "body") -> str:
    txt = clean_script_text(s)
    if not txt:
        return txt

    replacements = {
        "Gather 'round, adventurers": "Table setup",
        "Gather round, adventurers": "Table setup",
        "haunting world": "encounter",
        "delve into": "run",
    }
    for old, new in replacements.items():
        txt = txt.replace(old, new)

    txt = txt.replace("Dungeon Masters:", "DMs:")
    txt = txt.replace("Player Characters:", "Players:")

    txt = re.sub(
        r"Table setup[—-]let's run the encounter of the ([A-Za-z][A-Za-z\- ]+)\.",
        r"Table setup: \1 encounter.",
        txt,
        flags=re.IGNORECASE,
    )

    # Fix dangling possessives like "against the Zombie's."
    txt = re.sub(r"([A-Za-z])'s\.$", r"\1.", txt)

    if segment == "hook":
        parts = split_sentences(txt)
        if parts:
            txt = parts[0]
        txt = short(txt, 110, add_ellipsis=False)
    elif segment == "cta":
        if len(txt) > 190:
            trimmed = txt[:190]
            cut = trimmed.rfind(" ")
            if cut > 0:
                trimmed = trimmed[:cut]
            txt = trimmed.rstrip().rstrip(",;:-") + "."

    return clean_script_text(txt)


def is_generic_hook(text: str) -> bool:
    t = (text or "").strip().lower()
    bad = [
        "explore the moral dilemma",
        "gather 'round",
        "gather round",
        "delve into",
        "haunting world",
        "shine a light on",
    ]
    return any(b in t for b in bad)


def is_generic_cta(text: str) -> bool:
    t = (text or "").strip().lower()
    bad = [
        "create a tense environment",
        "challenge players to decide",
        "weigh their choices",
        "in your next session",
    ]
    return any(b in t for b in bad)

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

def build_monster_body(angle: str, fields: dict, traits: list, actions: list, attacks: list, day: str = ""):
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
        lead = deterministic_pick([
            f"{name} wins by doing its simple job ruthlessly.",
            f"{name} is scary when you let it run its plan for two rounds.",
            f"Against {name}, the fight swings when its first pressure cycle lands.",
        ], f"mon|{day}|{name}|{angle}|lead")
        close = deterministic_pick([
            "Play it fast: force one bad choice, then punish it.",
            "Run it with intent: one mistake from the party should cost real position.",
            "Push tempo early and make the table solve pressure, not just HP.",
        ], f"mon|{day}|{name}|{angle}|close")
        bits = [lead]
        if anchor:
            bits.append(anchor + ".")
        if action_blob:
            bits.append("Key moves: " + action_blob + ".")
        if trait_line:
            bits.append(trait_line)
        if nug:
            bits.append(nug)
        bits.append(close)
        return " ".join(bits)

    if angle == "common_mistake":
        lead = deterministic_pick([
            f"Common mistake vs {name}: treating it like ‘just flavor.’",
            f"Most tables misplay {name} by giving it free setup.",
            f"The usual error against {name} is fighting on its terms.",
        ], f"mon|{day}|{name}|{angle}|lead")
        close = deterministic_pick([
            "If the party ignores positioning, this thing gets free value.",
            "If they cluster or drift, it cashes in immediately.",
            "One lazy turn gives it momentum that costs resources to recover.",
        ], f"mon|{day}|{name}|{angle}|close")
        bits = [lead]
        if anchor:
            bits.append(anchor + ".")
        if action_blob:
            bits.append("What actually hurts: " + action_blob + ".")
        if trait_line:
            bits.append(trait_line)
        if nug:
            bits.append(nug)
        bits.append(close)
        return " ".join(bits)

    if angle == "counterplay":
        lead = deterministic_pick([
            f"Counterplay for {name}: deny its preferred fight.",
            f"Best answer to {name}: break the shape of the fight it wants.",
            f"Versus {name}, play denial first and damage second.",
        ], f"mon|{day}|{name}|{angle}|lead")
        close = deterministic_pick([
            "Use terrain, spacing, and focus-fire to remove its turns from the board.",
            "Control lanes, isolate targets, and collapse one threat at a time.",
            "Win the map first; the hit points follow.",
        ], f"mon|{day}|{name}|{angle}|close")
        bits = [lead]
        if anchor:
            bits.append(anchor + ".")
        if action_blob:
            bits.append("Watch for: " + action_blob + ".")
        if nug:
            bits.append(nug)
        bits.append(close)
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

def build_encounter_body(angle: str, fields: dict, traits: list, actions: list, day: str = ""):
    name = fields.get("name") or "This encounter anchor"
    anchor = creature_anchor(fields)
    angle = (angle or "").strip().lower()

    if angle == "three_beats":
        lead = deterministic_pick([
            f"Three-beat encounter seed: reveal {name}, escalate pressure, then force a hard choice.",
            f"Run this in three beats with {name}: warning, pressure spike, irreversible decision.",
            f"Build a three-step scene around {name}: clue, escalation, consequence.",
        ], f"enc|{day}|{name}|{angle}|lead")
    elif angle == "twist":
        lead = deterministic_pick([
            f"Twist for a {name} encounter: change the objective mid-scene, not just the hit points.",
            f"Encounter twist with {name}: the win condition shifts once the party commits.",
            f"Use {name} for a midpoint twist that rewrites priorities, not stats.",
        ], f"enc|{day}|{name}|{angle}|lead")
    elif angle == "terrain_feature":
        lead = deterministic_pick([
            f"Terrain feature seed with {name}: make the map itself a problem to solve.",
            f"Map-first encounter with {name}: terrain should matter every round.",
            f"Anchor this {name} scene on one terrain feature the party cannot ignore.",
        ], f"enc|{day}|{name}|{angle}|lead")
    elif angle == "time_pressure":
        lead = deterministic_pick([
            f"Time pressure seed for {name}: each round lost should cost position, resources, or civilians.",
            f"Against {name}, put a clock on the scene and charge interest every round.",
            f"Use {name} with a visible timer so indecision becomes the real damage source.",
        ], f"enc|{day}|{name}|{angle}|lead")
    elif angle == "moral_choice":
        lead = deterministic_pick([
            f"Moral-choice seed with {name}: success should ask what the party is willing to sacrifice.",
            f"Frame {name} as a values test: they can save everything, or they can win cleanly—not both.",
            f"Use {name} to force a moral fork where every path has a cost.",
        ], f"enc|{day}|{name}|{angle}|lead")
    else:
        lead = deterministic_pick([
            f"Encounter seed using {name}: set stakes before the first roll.",
            f"Build this {name} scene around stakes the party can name in one sentence.",
            f"Open with stakes, then let {name} test the table's priorities.",
        ], f"enc|{day}|{name}|{angle}|lead")

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
    bits.append(deterministic_pick([
        "Give players one clear clue and one costly decision.",
        "Telegraph one danger, then make the next choice expensive.",
        "Show the consequence early so their decision actually matters.",
    ], f"enc|{day}|{name}|{angle}|close"))
    return " ".join(bits)

def build_encounter_hook(angle: str, fields: dict, day: str = "") -> str:
    name = fields.get("name") or "This encounter"
    a = (angle or "").strip().lower()
    ctx = creature_context(name, fields)
    arena = ctx.get("arena") or "a scene where positioning and pressure matter"
    choice = ctx.get("choice") or "which cost they can live with"
    pressure = ctx.get("pressure") or "the action economy"

    if a == "moral_choice":
        return deterministic_pick([
            f"Run {name} as a moral-choice encounter: they can protect everyone, or finish the objective before the cost spikes.",
            f"Use {name} as a values test: give the table two wins, then make them choose which one they can actually keep.",
            f"Open a {name} scene with stakes on both sides, then force a choice that costs something either way.",
        ], f"hook|{day}|encounter_seed|{a}|{name}")

    if a == "time_pressure":
        return deterministic_pick([
            f"Put {name} in {arena} and start a visible clock—every delay should make {pressure} worse.",
            f"Frame a {name} encounter with a timer so the party must trade certainty for speed.",
            f"Run {name} with a hard clock and consequences each round; indecision should hurt more than damage.",
        ], f"hook|{day}|encounter_seed|{a}|{name}")

    if a == "terrain_feature":
        return deterministic_pick([
            f"Build this {name} encounter around terrain that changes decisions, not just movement.",
            f"Anchor {name} in {arena} so map control decides the fight before raw DPR does.",
            f"Run {name} where terrain creates risk every turn and rewards smart positioning.",
        ], f"hook|{day}|encounter_seed|{a}|{name}")

    return deterministic_pick([
        f"Use {name} as an encounter seed with clear stakes and one hard decision about {choice}.",
        f"Open with stakes, then let {name} pressure the table into a costly decision.",
        f"Frame {name} as a scene where priorities collide and every win has a price.",
    ], f"hook|{day}|encounter_seed|{a}|{name}")

def should_force_encounter_hook(hook: str, angle: str) -> bool:
    t = (hook or "").strip().lower()
    if not t:
        return True

    if is_generic_hook(t):
        return True

    gear_leaks = [
        "gear", "loadout", "equipment", "inventory", "shopping", "price tag", "kit",
    ]
    if any(tok in t for tok in gear_leaks):
        return True

    encounter_signals = [
        "encounter", "scene", "stakes", "objective", "pressure", "clock", "choice", "cost",
    ]
    if not any(tok in t for tok in encounter_signals):
        return True

    if (angle or "").strip().lower() == "moral_choice":
        moral_signals = ["choice", "cost", "sacrifice", "values", "save", "protect"]
        if not any(tok in t for tok in moral_signals):
            return True

    return False

def enforce_encounter_hook_guard(atom: dict, fact: dict, script: dict, day: str = "") -> dict:
    category = canonical_category(atom.get("category"))
    kind = (fact.get("kind") or "").strip().lower()
    angle = atom.get("angle") or ""

    if category != "encounter_seed" or kind != "creature":
        return script

    if should_force_encounter_hook(script.get("hook", ""), angle):
        fields = fact.get("fields") or {}
        script["hook"] = clean_script_text(build_encounter_hook(angle, fields, day=day))
        ai_diag("Encounter hook replaced by category hard-guard")

    return script

def build_encounter_cta(angle: str, fields: dict, day: str = "") -> str:
    name = fields.get("name") or "this encounter"
    a = (angle or "").strip().lower()
    ctx = creature_context(name, fields)
    pressure = ctx.get("pressure") or "position and action economy"

    if a == "moral_choice":
        return deterministic_pick([
            f"DMs: by round 2, force a hard choice—protect people now or secure the objective before losses escalate.",
            f"DMs: make them choose what they can live with: save everyone at higher risk, or end the threat before collateral climbs.",
            f"DMs: write two good outcomes and require one sacrifice; this scene should not allow a clean, total win.",
        ], f"cta_guard|{day}|encounter_seed|{a}|{name}")

    if a == "time_pressure":
        return deterministic_pick([
            f"DMs: keep a visible timer and make each delay worsen {pressure}.",
            f"DMs: charge interest every round so indecision costs more than bad rolls.",
            f"DMs: announce the clock up front, then make every late turn materially worse.",
        ], f"cta_guard|{day}|encounter_seed|{a}|{name}")

    if a == "terrain_feature":
        return deterministic_pick([
            "DMs: tie success to one terrain control point and make ignoring it immediately costly.",
            "DMs: make map control the objective so movement choices matter every round.",
            "DMs: pick one terrain feature that decides tempo if either side controls it.",
        ], f"cta_guard|{day}|encounter_seed|{a}|{name}")

    if a == "twist":
        return deterministic_pick([
            "DMs: flip the objective once they commit, then reward fast adaptation.",
            "DMs: change the win condition at midpoint so the first plan cannot finish cleanly.",
            "DMs: reveal a midpoint twist that shifts priorities instead of just adding HP.",
        ], f"cta_guard|{day}|encounter_seed|{a}|{name}")

    return deterministic_pick([
        "DMs: telegraph stakes early, then force one costly decision before round 3.",
        "DMs: show consequence first and make commitment expensive.",
        "DMs: set clear stakes and make delay hurt quickly.",
    ], f"cta_guard|{day}|encounter_seed|{a}|{name}")

def should_force_encounter_cta(cta: str, angle: str) -> bool:
    t = (cta or "").strip().lower()
    a = (angle or "").strip().lower()
    if not t:
        return True

    if is_generic_cta(t):
        return True

    if a == "moral_choice":
        terrain_leaks = ["terrain", "map feature", "control point", "chokepoint", "hazardous terrain"]
        if any(tok in t for tok in terrain_leaks):
            return True

        required_tradeoff = ["objective", "protect", "save", "sacrifice", "cost", "loss"]
        if not any(tok in t for tok in required_tradeoff):
            return True

    return False

def enforce_encounter_cta_guard(atom: dict, fact: dict, script: dict, day: str = "") -> dict:
    category = canonical_category(atom.get("category"))
    kind = (fact.get("kind") or "").strip().lower()
    angle = atom.get("angle") or ""

    if category != "encounter_seed" or kind != "creature":
        return script

    if should_force_encounter_cta(script.get("cta", ""), angle):
        fields = fact.get("fields") or {}
        script["cta"] = clean_script_text(build_encounter_cta(angle, fields, day=day))
        ai_diag("Encounter CTA replaced by category hard-guard")

    return script

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

    day = atom.get("day") or datetime.now().strftime("%Y-%m-%d")

    if category == "item_spotlight" and kind == "item":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name, angle=angle or "", day=day)
        body = build_item_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta, day=day)

    elif category == "monster_tactic" and kind == "creature":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name, angle=angle or "", day=day)
        body = build_monster_body(angle, fields, fact.get("traits") or [], fact.get("actions") or [], fact.get("attacks") or [], day=day)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta, day=day)

    elif category == "spell_use_case" and kind == "spell":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name, angle=angle or "", day=day)
        body = build_spell_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta, day=day)

    elif category == "encounter_seed" and kind == "creature":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name, angle=angle or "", day=day)
        body = build_encounter_body(angle, fields, fact.get("traits") or [], fact.get("actions") or [], day=day)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta, day=day)

    elif category in ("rules_ruling", "rules_myth") and kind == "rule":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name, angle=angle or "", day=day)
        body = build_rule_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta, day=day)

    elif category == "character_micro_tip" and kind == "class":
        hook, cta = pick_voice_lines(style_cfg, voice_name, category, name, angle=angle or "", day=day)
        body = build_class_body(angle, fields)
        script["hook"], script["body"], script["cta"] = hook, body, build_contextual_cta(category, angle, kind, name, fields, cta, day=day)

    else:
        print(f"ERROR: Unsupported category/kind: {category}/{kind}", file=sys.stderr)
        sys.exit(4)

    for key in ("hook", "body", "cta"):
        script[key] = clean_script_text(script.get(key, ""))

    script = maybe_ai_polish_script(atom, fact, style, script)
    atom["script"] = script

    script["cta"] = maybe_ai_polish_cta(atom, fact, style, script)
    script["cta"] = clean_script_text(script.get("cta", ""))
    script = enforce_encounter_hook_guard(atom, fact, script, day=day)
    script = enforce_encounter_cta_guard(atom, fact, script, day=day)

    full_text = f"{script.get('hook','').strip()}\n{script.get('body','').strip()}\n{script.get('cta','').strip()}\n"
    atom["script_id"] = sha256_text(full_text)
    atom["content"] = build_content_contract(atom, atom["script_id"], script, fact, style)

    atomic_write_json(ATOM_PATH, atom)
    print(ATOM_PATH)

if __name__ == "__main__":
    main()
