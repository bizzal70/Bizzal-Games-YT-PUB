#!/usr/bin/env python3
import json, os, sys, subprocess, hashlib, random
from datetime import datetime, UTC

try:
    import yaml
except ImportError:
    yaml = None

from reference_paths import resolve_active_srd_path, resolve_srd_pdf_path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

CONFIG_DIR   = os.path.join(REPO_ROOT, "config")
DATA_DIR     = os.path.join(REPO_ROOT, "data")
INCOMING_DIR = os.path.join(DATA_DIR, "atoms", "incoming")
VALID_DIR    = os.path.join(DATA_DIR, "atoms", "validated")
FAILED_DIR   = os.path.join(DATA_DIR, "atoms", "failed")

TOPIC_SPINE  = os.path.join(CONFIG_DIR, "topic_spine.yaml")
SCHEMA_MIN   = os.path.join(CONFIG_DIR, "atom_schema_min.json")
REF_CFG      = os.path.join(CONFIG_DIR, "reference_sources.yaml")

DOW_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

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

def load_topic_spine():
    if not os.path.exists(TOPIC_SPINE) or yaml is None:
        return {}
    try:
        with open(TOPIC_SPINE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def weighted_choice(weights: dict, seed_key: str):
    items = [(k, int(v)) for k, v in (weights or {}).items() if int(v) > 0]
    if not items:
        return None
    total = sum(v for _, v in items)
    rng = random.Random(int(sha256_text(seed_key)[:8], 16))
    roll = rng.randint(1, total)
    acc = 0
    for k, w in items:
        acc += w
        if roll <= acc:
            return k
    return items[0][0]

def pick_category_and_angle_for_day(day_str: str):
    spine = load_topic_spine()

    # Preferred model: weekly_spine + category_weights.<category>.angles
    wk = spine.get("weekly_spine") if isinstance(spine, dict) else {}
    cw = spine.get("category_weights") if isinstance(spine, dict) else {}

    if isinstance(wk, dict) and wk:
        dow = DOW_KEYS[datetime.now().weekday()]
        category = wk.get(dow)
        if category:
            angle_weights = ((cw.get(category) or {}).get("angles") or {}) if isinstance(cw, dict) else {}
            angle = weighted_choice(angle_weights, f"angle|{day_str}|{category}") if angle_weights else None
            return category, angle

    # Legacy fallback: schedule list
    schedule = spine.get("schedule") if isinstance(spine, dict) else None
    if isinstance(schedule, list) and schedule:
        weights = {}
        for row in schedule:
            if not isinstance(row, dict):
                continue
            cat = row.get("category")
            if not cat:
                continue
            weights[str(cat)] = int(row.get("weight", 1))
        category = weighted_choice(weights, f"topic|{day_str}") if weights else None
        return category, None

    return "monster_tactic", None

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

    # Category/angle come from topic spine weekly schedule + weighted angles.
    picked_category, picked_angle = pick_category_and_angle_for_day(DAY)
    atom["category"] = picked_category or atom.get("category") or "monster_tactic"
    if picked_angle:
        atom["angle"] = picked_angle
    elif not atom.get("angle"):
        atom["angle"] = "how_it_wins"

    # Always wipe picks + script/fact if rerunning (prevents stale data)
    clear_irrelevant_picks(atom)
    atom["fact"] = {}
    atom["script"] = {}
    atom["script_id"] = None

    active_srd_path, _ = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    srd_pdf_path, _ = resolve_srd_pdf_path(REPO_ROOT, REF_CFG)
    atom.setdefault("source", {})
    atom["source"]["active_srd_path"] = active_srd_path
    atom["source"]["srd_pdf_path"] = srd_pdf_path

    atomic_write_json(ATOM_PATH, atom)

    # Fill picks (preferred broad-category picker), fallback to legacy per-category pickers.
    if has_exec("bin/core/fill_picks.py"):
        run([os.path.join(REPO_ROOT, "bin/core/fill_picks.py")])
    else:
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
