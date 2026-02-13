#!/usr/bin/env python3
import json
import os
import hashlib
from datetime import datetime, timezone
from collections import Counter, defaultdict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
OUT_DIR = os.path.join(REPO_ROOT, "data", "reference_inventory")
REF_CFG = os.path.join(REPO_ROOT, "config", "reference_sources.yaml")

from reference_paths import resolve_active_srd_path

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    active_srd, _cfg = resolve_active_srd_path(REPO_ROOT, REF_CFG)
    if not active_srd or not os.path.isdir(active_srd):
        raise SystemExit(f"ERROR: Active SRD path not found: {active_srd}")

    files = sorted([f for f in os.listdir(active_srd) if f.endswith(".json")])
    inventory = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_srd_path": os.path.realpath(active_srd),
        "file_count": len(files),
        "files": {}
    }

    md_lines = []
    md_lines.append(f"# ACTIVE_WOTC_SRD Inventory")
    md_lines.append(f"- Generated (UTC): {inventory['generated_utc']}")
    md_lines.append(f"- Path: `{inventory['active_srd_path']}`")
    md_lines.append(f"- JSON files: {inventory['file_count']}")
    md_lines.append("")

    # manifest sha256 lines
    manifest_lines = []

    for fname in files:
        path = os.path.join(active_srd, fname)
        st = os.stat(path)
        size = st.st_size
        sha = sha256_file(path)
        manifest_lines.append(f"{sha}  {fname}")

        data = load_json(path)

        # Django fixtures are usually a list of records: {model, pk, fields}
        rec_count = len(data) if isinstance(data, list) else None

        model_counter = Counter()
        field_keys_counter = Counter()

        sample = None
        if isinstance(data, list) and data:
            sample = data[0]
            for rec in data:
                if isinstance(rec, dict):
                    m = rec.get("model")
                    if m: model_counter[m] += 1
                    fields = rec.get("fields")
                    if isinstance(fields, dict):
                        field_keys_counter.update(fields.keys())

        # top field keys (most common)
        top_fields = field_keys_counter.most_common(25)

        inventory["files"][fname] = {
            "bytes": size,
            "sha256": sha,
            "record_count": rec_count,
            "models": dict(model_counter),
            "top_field_keys": top_fields,
            "sample_record": sample
        }

        md_lines.append(f"## {fname}")
        md_lines.append(f"- Size: {size:,} bytes")
        md_lines.append(f"- SHA256: `{sha}`")
        md_lines.append(f"- Records: {rec_count}")
        if model_counter:
            md_lines.append(f"- Models: {', '.join([f'{k} ({v})' for k,v in model_counter.most_common(5)])}")
        if top_fields:
            md_lines.append(f"- Top fields: {', '.join([k for k,_ in top_fields[:12]])}")
        md_lines.append("")

    # write outputs
    inv_path = os.path.join(OUT_DIR, "active_files.json")
    md_path  = os.path.join(OUT_DIR, "active_summary.md")
    man_path = os.path.join(OUT_DIR, "active_manifest.sha256")

    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        f.write("\n")

    with open(man_path, "w", encoding="utf-8") as f:
        f.write("\n".join(manifest_lines))
        f.write("\n")

    print(inv_path)
    print(md_path)
    print(man_path)

if __name__ == "__main__":
    main()
