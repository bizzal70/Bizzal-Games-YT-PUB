#!/usr/bin/env python3
import json, os, random, sys
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

def main():
    if not os.path.exists(ATOM_PATH):
        print(f"ERROR: Atom not found: {ATOM_PATH}", file=sys.stderr)
        sys.exit(3)

    cfg = load_yaml(CFG_PATH) or {}
    defaults = cfg.get("defaults") or {}
    cat_rules = (cfg.get("category_rules") or {})

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
    tones  = list((defaults.get("tones") or ["neutral"]))

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

    angle = choose_avoid(angles, prev.get("angle"))
    voice = choose_avoid(voices, prev.get("voice"))
    tone  = random.choice(tones)

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
        "spice": spice,
        "length": defaults.get("length", "shorts"),
        "seed": f"{day}|{category}"
    }

    atomic_write_json(ATOM_PATH, atom)

    # update history
    hist.setdefault(day, {})
    hist[day][category] = {"angle": angle, "voice": voice, "tone": tone, "spice": spice}
    atomic_write_json(HIST_PATH, hist)

    print(ATOM_PATH)

if __name__ == "__main__":
    main()
