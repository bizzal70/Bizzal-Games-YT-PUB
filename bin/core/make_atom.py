#!/usr/bin/env python3
import json, os, sys, subprocess, hashlib, random
from datetime import datetime, UTC

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

CONFIG_DIR   = os.path.join(REPO_ROOT, "config")
DATA_DIR     = os.path.join(REPO_ROOT, "data")
INCOMING_DIR = os.path.join(DATA_DIR, "atoms", "incoming")
VALID_DIR    = os.path.join(DATA_DIR, "atoms", "validated")
FAILED_DIR   = os.path.join(DATA_DIR, "atoms", "failed")

TOPIC_SPINE  = os.path.join(CONFIG_DIR, "topic_spine.yaml")
SCHEMA_MIN   = os.path.join(CONFIG_DIR, "atom_schema_min.json")

DAY = datetime.now().strftime("%Y-%m-%d")
ATOM_PATH = os.path.join(INCOMING_DIR, f"{DAY}.json")

def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    raise SystemExit(code)

def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def run(cmd, check=True):
    # cmd can be list or string
    if isinstance(cmd, str):
        cmd = cmd.split()
    r = subprocess.run(cmd, cwd=REPO_ROOT)
    if check and r.returncode != 0:
        die(f"[make_atom] command failed ({r.returncode}): {' '.join(cmd)}")
    return r.returncode

def has_exec(path_rel: str) -> bool:
    p = os.path.join(REPO_ROOT, path_rel)
    return os.path.exists(p) and os.access(p, os.X_OK)

def ensure_dirs():
    for d in [INCOMING_DIR, VALID_DIR, FAILED_DIR]:
        os.makedirs(d, exist_ok=True)

# ---------- topic spine parsing ----------

def parse_topic_spine_categories():
    """
    Try YAML (PyYAML) if available, else fallback to a simple parser:
    expects something like:
      schedule:
        - category: item_spotlight
          weight: 3
        - category: monster_tactic
          weight: 2
    """
    if not os.path.exists(TOPIC_SPINE):
        # Safe default if file missing
        return [("item_spotlight", 1), ("monster_tactic", 1), ("spell_use_case", 1), ("rule_clarification", 1)]

    # Try PyYAML first
    try:
        import yaml  # type: ignore
        obj = yaml.safe_load(open(TOPIC_SPINE, "r", encoding="utf-8"))
        # Accept either top-level list or schedule key
        rows = obj.get("schedule", obj) if isinstance(obj, dict) else obj
        out = []
        if isinstance(rows, list):
            for r in rows:
                if not isinstance(r, dict):
                    continue
                cat = r.get("category")
                w = r.get("weight", 1)
                if cat:
                    out.append((str(cat), int(w)))
        if out:
            return out
    except Exception:
        pass

    # Fallback: very small “good enough” parser for category/weight pairs
    out = []
    cat = None
    w = 1
    for line in open(TOPIC_SPINE, "r", encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("category:"):
            cat = s.split(":", 1)[1].strip().strip("'\"")
        elif s.startswith("weight:"):
            try:
                w = int(s.split(":", 1)[1].strip())
            except Exception:
                w = 1
        # If we have a cat, emit when we hit next "-" or end-ish; easiest: emit when both seen
        if cat is not None and "weight:" in s:
            out.append((cat, w))
            cat, w = None, 1

    if out:
        return out

    # Last resort
    return [("item_spotlight", 1), ("monster_tactic", 1), ("spell_use_case", 1), ("rule_clarification", 1)]

def pick_category_for_day(day_str: str):
    cats = parse_topic_spine_categories()
    # deterministic seed per day
    seed = int(sha256_text("topic|" + day_str)[:8], 16)
    rng = random.Random(seed)

    # weighted pick
    total = sum(max(1, w) for _, w in cats)
    roll = rng.randint(1, total)
    acc = 0
    for cat, w in cats:
        acc += max(1, w)
        if roll <= acc:
            return cat
    return cats[0][0]

# ---------- atom creation / validation ----------

def new_atom(day_str: str):
    return {
                "day": day_str,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),
        "category": None,
        "angle": None,
        "style": {},
        "picks": {
            "creature_pk": None,
            "spell_pk": None,
            "item_pk": None,
            "rule_pk": None,
            "class_pk": None
        }
    }

def clear_irrelevant_picks(atom: dict):
    cat = (atom.get("category") or "").lower()
    picks = atom.get("picks", {})
    # Default: clear everything, then the picker will set the right pk
    for k in list(picks.keys()):
        picks[k] = None

    # If category implies a target type, keep its key as None (picker will fill)
    # This function is mostly about wiping stale picks when you switch categories.
    atom["picks"] = picks

def minimal_validate(atom: dict):
    # Minimal “shape” validation (keeps you from shipping junk)
    required_top = ["day", "created_at", "category", "angle", "style", "picks", "fact", "script", "script_id"]
    for k in required_top:
        if k not in atom:
            return False, f"missing key: {k}"

    if not isinstance(atom["picks"], dict):
        return False, "picks not dict"
    if not isinstance(atom["fact"], dict):
        return False, "fact not dict"
    if not isinstance(atom["script"], dict):
        return False, "script not dict"

    for k in ["hook", "body", "cta"]:
        if k not in atom["script"] or not str(atom["script"].get(k, "")).strip():
            return False, f"script missing/blank: {k}"

    # script_id integrity check
    s = atom["script"]
    packed = f"{s.get('hook','').strip()}\n{s.get('body','').strip()}\n{s.get('cta','').strip()}\n"
    expect = sha256_text(packed)
    if atom.get("script_id") != expect:
        return False, "script_id does not match script content"

    return True, "ok"

def load_schema_min_ok():
    # optional: ensure file exists; we’re not full jsonschema-validating yet
    return os.path.exists(SCHEMA_MIN)

# ---------- pipeline orchestration ----------

def pickers_for_category(cat: str):
    c = (cat or "").lower()
    # Map your categories to picker scripts (add more here as you add categories)
    if "spell" in c:
        return ["bin/core/pick_spell.py"]
    if "monster" in c or "creature" in c:
        return ["bin/core/pick_creature.py"]
    if "item" in c or "gear" in c:
        return ["bin/core/pick_item.py"]
    if "rule" in c:
        return ["bin/core/pick_rule.py"]
    if "class" in c:
        return ["bin/core/pick_class.py"]
    # fallback: try item (safe / broad)
    return ["bin/core/pick_item.py"]

def safe_move(src, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    base = os.path.basename(src)
    dst = os.path.join(dst_dir, base)
    os.replace(src, dst)
    return dst

def main():
    ensure_dirs()

    # Create or load today's atom
    if os.path.exists(ATOM_PATH):
        atom = load_json(ATOM_PATH)
    else:
        atom = new_atom(DAY)
        atomic_write_json(ATOM_PATH, atom)

    # Ensure baseline schema file exists (optional but recommended)
    if not load_schema_min_ok():
        print("[make_atom] WARNING: config/atom_schema_min.json not found; continuing with minimal validation", file=sys.stderr)

    # Pick category deterministically from topic spine (unless already set)
    if not atom.get("category"):
        atom["category"] = pick_category_for_day(DAY)

    # If angle missing, set a deterministic default by category
    if not atom.get("angle"):
        # common set used in your scripts
        angles = ["best_moment", "common_misplay", "dm_twist", "how_it_wins", "counterplay", "story_hook"]
        seed = int(sha256_text("angle|" + DAY + "|" + atom["category"])[:8], 16)
        atom["angle"] = random.Random(seed).choice(angles)

    # Always wipe picks + script/fact if rerunning (prevents stale data)
    clear_irrelevant_picks(atom)
    atom["fact"] = {}
    atom["script"] = {}
    atom["script_id"] = None
    atomic_write_json(ATOM_PATH, atom)

    # Run picker(s)
    for picker in pickers_for_category(atom["category"]):
        if not has_exec(picker):
            die(f"[make_atom] missing picker executable: {picker} (chmod +x? file exists?)")
        run([os.path.join(REPO_ROOT, picker)])

    # Attach fact, pick style, write script
    for step in ["bin/core/attach_fact.py", "bin/core/pick_style.py", "bin/core/write_script_from_fact.py"]:
        if not has_exec(step):
            die(f"[make_atom] missing step executable: {step}")
        run([os.path.join(REPO_ROOT, step)])

    # Validate and route atom
    atom = load_json(ATOM_PATH)
    ok, msg = minimal_validate(atom)
    if ok:
        dst = safe_move(ATOM_PATH, VALID_DIR)
        print(dst)
        return

    # On failure: mark and move to failed
    atom.setdefault("errors", [])
    atom["errors"].append({
        "at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00","Z"),
        "error": msg
    })
    atomic_write_json(ATOM_PATH, atom)
    dst = safe_move(ATOM_PATH, FAILED_DIR)
    die(f"[make_atom] validation failed: {msg}\nMoved to: {dst}", 2)

if __name__ == "__main__":
    main()
