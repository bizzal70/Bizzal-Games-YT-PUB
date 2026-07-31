import json, os, hashlib

REPO_ROOT = os.path.abspath(".")

TARGETS = [
    {"key": "fey-wanderer", "day": "2026-07-31-regen-fey-wanderer"},
    {"key": "awakened-tree", "day": "2026-07-31-regen-awakened-tree"},
]


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def minimal_validate(atom):
    required_top = ["day", "created_at", "category", "angle", "style", "picks", "fact", "script", "script_id", "content"]
    for k in required_top:
        if k not in atom:
            return False, f"missing key: {k}"
    for k in ["hook", "body", "cta"]:
        if k not in atom["script"] or not str(atom["script"].get(k, "")).strip():
            return False, f"script missing/blank: {k}"
    s = atom["script"]
    packed = f"{s.get('hook','').strip()}\n{s.get('body','').strip()}\n{s.get('cta','').strip()}\n"
    expect = sha256_text(packed)
    if atom.get("script_id") != expect:
        return False, "script_id does not match script content"
    content_required = ["content_id", "episode_id", "month_id", "month_bundle_id", "canonical_hash", "script_id", "asset_contract", "segments", "tags"]
    for k in content_required:
        if k not in atom["content"]:
            return False, f"content missing key: {k}"
    if atom["content"].get("script_id") != atom.get("script_id"):
        return False, "content.script_id does not match script_id"
    segments = atom["content"].get("segments") or {}
    for k in ["hook", "body", "cta"]:
        seg = segments.get(k)
        if not isinstance(seg, dict):
            return False, f"content.segments missing: {k}"
        if not str(seg.get("segment_id", "")).strip():
            return False, f"segment missing segment_id: {k}"
        if not str(seg.get("voice_track_id", "")).strip():
            return False, f"segment missing voice_track_id: {k}"
        if not str(seg.get("visual_asset_id", "")).strip():
            return False, f"segment missing visual_asset_id: {k}"
    return True, "ok"


results = []
for t in TARGETS:
    incoming = os.path.join(REPO_ROOT, f"data/atoms_regen_{t['key']}/incoming", t["day"] + ".json")
    validated_dir = os.path.join(REPO_ROOT, f"data/atoms_regen_{t['key']}/validated")
    os.makedirs(validated_dir, exist_ok=True)
    validated = os.path.join(validated_dir, t["day"] + ".json")

    with open(incoming, encoding="utf-8") as f:
        atom = json.load(f)

    ok, msg = minimal_validate(atom)
    results.append({"key": t["key"], "ok": ok, "msg": msg})
    if ok:
        os.replace(incoming, validated)

with open("_tmp_regen_validate_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(json.dumps(results, indent=2))
if not all(r["ok"] for r in results):
    raise SystemExit(1)
