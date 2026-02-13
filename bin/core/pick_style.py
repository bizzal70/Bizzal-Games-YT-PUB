#!/usr/bin/env python3
import hashlib, json, os, random, sys
from datetime import datetime, timedelta

try:
    import yaml
except ImportError:
    print("ERROR: Missing PyYAML. Install with: python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ATOM_PATH = os.path.join(REPO_ROOT, "data", "atoms", "incoming", datetime.now().strftime("%Y-%m-%d") + ".json")
CFG_PATH  = os.path.join(REPO_ROOT, "config", "style_rules.yaml")
STATE_DIR = os.path.join(REPO_ROOT, "runtime", "state")
HIST_PATH = os.path.join(STATE_DIR, "style_history.json")

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

def load_history():
    if not os.path.exists(HIST_PATH):
        return {}
    return load_json(HIST_PATH)


def pick_tts_voice(day: str, category: str, tone: str, style_voice: str, voiceover_cfg: dict, defaults: dict) -> str:
    base_default = ((defaults.get("voiceover_default") or {}).get("tts_voice_id") or "alloy")

    pool = voiceover_cfg.get("tts_voice_ids")
    if isinstance(pool, list):
        clean = [str(v).strip() for v in pool if str(v).strip()]
        if clean:
            seed = f"tts|{day}|{category}|{tone}|{style_voice}"
            digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % len(clean)
            return clean[idx]

    direct = str(voiceover_cfg.get("tts_voice_id") or "").strip()
    if direct:
        return direct

    return base_default

def main():
    if not os.path.exists(ATOM_PATH):
        print(f"ERROR: Atom not found: {ATOM_PATH}", file=sys.stderr)
        sys.exit(3)

    cfg = load_yaml(CFG_PATH) or {}
    defaults = cfg.get("defaults") or {}
    cat_rules = (cfg.get("category_rules") or {})
    persona_by_category = cfg.get("persona_by_category") or {}
    tones_by_category = cfg.get("tones_by_category") or {}
    voiceover_by_tone = cfg.get("voiceover_by_tone") or {}
    voiceover_by_voice = cfg.get("voiceover_by_voice") or {}

    atom = load_json(ATOM_PATH)
    category = atom.get("category")
    if category not in cat_rules:
        print(f"ERROR: No style rules for category: {category}", file=sys.stderr)
        sys.exit(4)

    # Deterministic seed per day+category
    day = datetime.now().strftime("%Y-%m-%d")
    random.seed(f"{day}|{category}")

    rules = cat_rules[category]
    angles = list(rules.get("angles") or [])
    voices = list(rules.get("voices") or [])
    category_tones = tones_by_category.get(category)
    if isinstance(category_tones, list) and category_tones:
        tones = list(category_tones)
    elif isinstance(category_tones, str) and category_tones.strip():
        tones = [category_tones.strip()]
    else:
        tones = list((defaults.get("tones") or ["neutral"]))

    if not angles or not voices:
        print(f"ERROR: style_rules missing angles/voices for {category}", file=sys.stderr)
        sys.exit(5)

    os.makedirs(STATE_DIR, exist_ok=True)
    hist = load_history()

    # yesterday’s style (if present)
    yday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    prev = (hist.get(yday) or {}).get(category) or {}

    def choose_avoid(options, avoid_value):
        opts = [o for o in options if o != avoid_value]
        return random.choice(opts) if opts else random.choice(options)

    chosen_angle = atom.get("angle")
    if chosen_angle in angles:
        angle = chosen_angle
    else:
        angle = choose_avoid(angles, prev.get("angle"))
    voice = choose_avoid(voices, prev.get("voice"))
    tone  = random.choice(tones)
    persona = persona_by_category.get(category) or defaults.get("persona_default") or "table_coach"

    voiceover = defaults.get("voiceover_default") or {}
    tone_vo = voiceover_by_tone.get(tone) if isinstance(voiceover_by_tone, dict) else None
    if isinstance(tone_vo, dict):
        merged = dict(voiceover)
        merged.update(tone_vo)
        voiceover = merged

    voice_vo = voiceover_by_voice.get(voice) if isinstance(voiceover_by_voice, dict) else None
    if isinstance(voice_vo, dict):
        merged = dict(voiceover)
        merged.update(voice_vo)
        voiceover = merged

    chosen_tts_voice = pick_tts_voice(day, category, tone, voice, voiceover, defaults)

    spice_rate = float(defaults.get("spice_rate", 0.0))
    spice_pool = ["dry_humor", "grim", "practical", "punchy"]
    spice = []
    if random.random() < spice_rate:
        spice = [random.choice(spice_pool)]

    # Write into atom
    atom["angle"] = angle
    atom["style"] = {
        "voice": voice,
        "tone": tone,
        "persona": persona,
        "voiceover": {
            "voice_pack_id": voiceover.get("voice_pack_id") or f"voice-{voice}",
            "tts_voice_id": chosen_tts_voice,
        },
        "spice": spice,
        "length": defaults.get("length", "shorts"),
        "seed": f"{day}|{category}"
    }

    atomic_write_json(ATOM_PATH, atom)

    # update history
    hist.setdefault(day, {})
    hist[day][category] = {"angle": angle, "voice": voice, "tone": tone, "persona": persona, "spice": spice}
    atomic_write_json(HIST_PATH, hist)

    print(ATOM_PATH)

if __name__ == "__main__":
    main()
