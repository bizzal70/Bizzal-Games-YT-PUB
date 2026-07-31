import json, os, subprocess, sys
from datetime import datetime, UTC

REPO_ROOT = os.path.abspath(".")

TARGETS = [
    {
        "key": "fey-wanderer",
        "system": "dnd5e",
        "day": "2026-07-31-regen-fey-wanderer",
        "category": "class_spotlight",
        "angle": "subclass_identity",
        "pick_key": "class_pk",
        "pick_val": "tashas-cauldron_fey-wanderer",
        "old_vid": "xOj74v5ekDQ",
    },
    {
        "key": "awakened-tree",
        "system": "dnd5e",
        "day": "2026-07-31-regen-awakened-tree",
        "category": "monster_tactic",
        "angle": "how_it_wins",
        "pick_key": "creature_pk",
        "pick_val": "srd-2024_awakened-tree",
        "old_vid": "xskRZfy8Vpc",
    },
]

results = []

for t in TARGETS:
    incoming_dir = os.path.join(REPO_ROOT, f"data/atoms_regen_{t['key']}/incoming")
    validated_dir = os.path.join(REPO_ROOT, f"data/atoms_regen_{t['key']}/validated")
    os.makedirs(incoming_dir, exist_ok=True)
    os.makedirs(validated_dir, exist_ok=True)

    env = os.environ.copy()
    env["BIZZAL_SYSTEM_ID"] = t["system"]
    env["BIZZAL_DAY"] = t["day"]
    env["BIZZAL_ATOM_INCOMING_DIR"] = incoming_dir
    env["BIZZAL_ATOM_VALIDATED_DIR"] = validated_dir

    atom = {
        "day": t["day"],
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "category": t["category"],
        "angle": t["angle"],
        "style": {},
        "picks": {
            "creature_pk": None, "spell_pk": None, "item_pk": None,
            "rule_pk": None, "class_pk": None,
        },
        "fact": {}, "script": {}, "script_id": None, "content": {},
    }
    atom["picks"][t["pick_key"]] = t["pick_val"]

    atom_path = os.path.join(incoming_dir, t["day"] + ".json")
    with open(atom_path, "w", encoding="utf-8") as f:
        json.dump(atom, f, indent=2, ensure_ascii=False)

    for step in ["bin/core/attach_fact.py", "bin/core/pick_style.py", "bin/core/write_script_from_fact.py"]:
        r = subprocess.run([sys.executable, os.path.join(REPO_ROOT, step)], env=env, cwd=REPO_ROOT)
        if r.returncode != 0:
            results.append({"key": t["key"], "old_vid": t["old_vid"], "error": f"{step} failed rc={r.returncode}"})
            break
    else:
        with open(atom_path, encoding="utf-8") as f:
            final_atom = json.load(f)
        script = final_atom.get("script", {})
        results.append({
            "key": t["key"], "old_vid": t["old_vid"],
            "hook": script.get("hook", ""), "body": script.get("body", ""), "cta": script.get("cta", ""),
            "fact_name": (final_atom.get("fact") or {}).get("name", ""),
        })

with open("_tmp_regen_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"processed {len(results)} targets")
