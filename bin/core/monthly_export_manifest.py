#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
VALIDATED_DIR = os.path.join(REPO_ROOT, "data", "atoms", "validated")
OUT_ROOT = os.path.join(REPO_ROOT, "data", "archive", "monthly")


def sha256_text(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def slugify(s: str) -> str:
    import re
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").strip().lower())
    txt = re.sub(r"-+", "-", txt).strip("-")
    return txt or "na"


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def build_markdown(manifest: dict) -> str:
    lines = []
    lines.append(f"# Monthly Export Manifest — {manifest['month']}")
    lines.append("")
    lines.append(f"- Generated (UTC): {manifest['generated_utc']}")
    lines.append(f"- Bundle ID: `{manifest['month_bundle_id']}`")
    lines.append(f"- Entries: {manifest['count']}")
    lines.append("")
    lines.append("## Entries")
    lines.append("")

    for entry in manifest.get("entries", []):
        lines.append(f"### {entry.get('day')} — {entry.get('title')}")
        lines.append(f"- Content ID: `{entry.get('content_id')}`")
        lines.append(f"- Episode ID: `{entry.get('episode_id')}`")
        lines.append(f"- Category: `{entry.get('category')}`")
        lines.append(f"- Angle: `{entry.get('angle')}`")
        lines.append(f"- Voice: `{entry.get('voice')}`")
        lines.append(f"- Script ID: `{entry.get('script_id')}`")
        hook_seg = (entry.get("segments") or {}).get("hook") or {}
        body_seg = (entry.get("segments") or {}).get("body") or {}
        cta_seg = (entry.get("segments") or {}).get("cta") or {}
        lines.append(
            "- Segment IDs: "
            f"hook `{hook_seg.get('segment_id')}`, "
            f"body `{body_seg.get('segment_id')}`, "
            f"cta `{cta_seg.get('segment_id')}`"
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args():
    ap = argparse.ArgumentParser(description="Generate monthly manifest for zine/export workflows.")
    ap.add_argument("--month", default=datetime.now().strftime("%Y-%m"), help="Month in YYYY-MM format (default: current month)")
    return ap.parse_args()


def derive_content_fallback(atom: dict) -> dict:
    day = atom.get("day") or datetime.now().strftime("%Y-%m-%d")
    month_id = day[:7]
    category = slugify(atom.get("category") or "")
    angle = slugify(atom.get("angle") or "")
    fact = atom.get("fact") or {}
    style = atom.get("style") or {}

    kind = slugify(fact.get("kind") or "unknown")
    fact_pk = slugify(str(fact.get("pk") or fact.get("name") or "unknown"))
    script_id = atom.get("script_id") or sha256_text(day + "|" + category + "|" + fact_pk)
    canonical = sha256_text(f"{day}|{category}|{kind}|{fact_pk}|{script_id}")
    short_hash = canonical[:12]

    content_id = f"bgp-{day}-{category}-{kind}-{fact_pk}-{short_hash}"
    return {
        "content_id": content_id,
        "episode_id": f"ep-{day}-{category}-{short_hash}",
        "month_id": month_id,
        "month_bundle_id": f"zine-{month_id}-{sha256_text(month_id)[:8]}",
        "script_id": script_id,
        "segments": {
            "hook": {
                "segment_id": f"seg-hook-{sha256_text(content_id + '|hook')[:10]}",
                "voice_track_id": f"vox-hook-{sha256_text(content_id + '|hook|voice')[:10]}",
                "visual_asset_id": f"img-hook-{sha256_text(content_id + '|hook|visual')[:10]}",
            },
            "body": {
                "segment_id": f"seg-body-{sha256_text(content_id + '|body')[:10]}",
                "voice_track_id": f"vox-body-{sha256_text(content_id + '|body|voice')[:10]}",
                "visual_asset_id": f"img-body-{sha256_text(content_id + '|body|visual')[:10]}",
            },
            "cta": {
                "segment_id": f"seg-cta-{sha256_text(content_id + '|cta')[:10]}",
                "voice_track_id": f"vox-cta-{sha256_text(content_id + '|cta|voice')[:10]}",
                "visual_asset_id": f"img-cta-{sha256_text(content_id + '|cta|visual')[:10]}",
            },
        },
        "tags": sorted({month_id, category, angle, kind, slugify(style.get("voice") or "friendly-vet"), "content_press", "shorts"}),
    }


def main():
    args = parse_args()
    month = args.month

    if len(month) != 7 or month[4] != "-":
        raise SystemExit("ERROR: --month must be YYYY-MM")

    if not os.path.isdir(VALIDATED_DIR):
        raise SystemExit(f"ERROR: missing validated dir: {VALIDATED_DIR}")

    entries = []
    for fname in sorted(os.listdir(VALIDATED_DIR)):
        if not fname.endswith(".json"):
            continue
        if not fname.startswith(month + "-"):
            continue

        atom = load_json(os.path.join(VALIDATED_DIR, fname))
        content = atom.get("content") or {}
        if not content.get("content_id"):
            content = derive_content_fallback(atom)
        script = atom.get("script") or {}
        fact = atom.get("fact") or {}
        style = atom.get("style") or {}

        segments = content.get("segments") or {}
        entries.append({
            "day": atom.get("day"),
            "content_id": content.get("content_id"),
            "episode_id": content.get("episode_id"),
            "month_bundle_id": content.get("month_bundle_id"),
            "category": atom.get("category"),
            "angle": atom.get("angle"),
            "voice": style.get("voice"),
            "script_id": atom.get("script_id"),
            "title": fact.get("name") or fact.get("kind") or "Untitled",
            "hook": script.get("hook", ""),
            "body": script.get("body", ""),
            "cta": script.get("cta", ""),
            "segments": {
                "hook": {
                    "segment_id": (segments.get("hook") or {}).get("segment_id"),
                    "voice_track_id": (segments.get("hook") or {}).get("voice_track_id"),
                    "visual_asset_id": (segments.get("hook") or {}).get("visual_asset_id"),
                },
                "body": {
                    "segment_id": (segments.get("body") or {}).get("segment_id"),
                    "voice_track_id": (segments.get("body") or {}).get("voice_track_id"),
                    "visual_asset_id": (segments.get("body") or {}).get("visual_asset_id"),
                },
                "cta": {
                    "segment_id": (segments.get("cta") or {}).get("segment_id"),
                    "voice_track_id": (segments.get("cta") or {}).get("voice_track_id"),
                    "visual_asset_id": (segments.get("cta") or {}).get("visual_asset_id"),
                },
            },
            "tags": content.get("tags") or [],
        })

    entries.sort(key=lambda e: e.get("day") or "")
    bundle_id = entries[0].get("month_bundle_id") if entries else f"zine-{month}-pending"

    manifest = {
        "month": month,
        "month_bundle_id": bundle_id,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(entries),
        "entries": entries,
    }

    out_dir = os.path.join(OUT_ROOT, month)
    os.makedirs(out_dir, exist_ok=True)

    json_out = os.path.join(out_dir, "manifest.json")
    md_out = os.path.join(out_dir, "manifest.md")

    atomic_write_json(json_out, manifest)
    with open(md_out, "w", encoding="utf-8") as f:
        f.write(build_markdown(manifest))

    print(json_out)
    print(md_out)


if __name__ == "__main__":
    main()
