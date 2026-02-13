#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import os
from datetime import datetime


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
MONTHLY_ROOT = os.path.join(REPO_ROOT, "data", "archive", "monthly")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args():
    ap = argparse.ArgumentParser(description="Generate zine pack files from monthly manifest.")
    ap.add_argument("--month", default=datetime.now().strftime("%Y-%m"), help="Month in YYYY-MM format")
    ap.add_argument("--manifest", default="", help="Optional explicit manifest.json path")
    return ap.parse_args()


def manifest_path_for_month(month: str) -> str:
    return os.path.join(MONTHLY_ROOT, month, "manifest.json")


def segment_record(entry: dict, segment_name: str, raw_segment):
    if isinstance(raw_segment, dict):
        return {
            "segment_id": raw_segment.get("segment_id"),
            "voice_track_id": raw_segment.get("voice_track_id"),
            "visual_asset_id": raw_segment.get("visual_asset_id"),
        }

    # Legacy manifests store segment IDs as plain strings.
    if isinstance(raw_segment, str) and raw_segment.strip():
        segment_id = raw_segment.strip()
    else:
        content_id = entry.get("content_id") or "unknown"
        segment_id = f"seg-{segment_name}-{hashlib.sha256((content_id + '|' + segment_name).encode('utf-8')).hexdigest()[:10]}"

    return {
        "segment_id": segment_id,
        "voice_track_id": f"vox-{segment_name}-{hashlib.sha256((segment_id + '|voice').encode('utf-8')).hexdigest()[:10]}",
        "visual_asset_id": f"img-{segment_name}-{hashlib.sha256((segment_id + '|visual').encode('utf-8')).hexdigest()[:10]}",
    }


def write_content_md(out_path: str, manifest: dict):
    lines = []
    lines.append(f"# Bizzal Monthly Zine Draft — {manifest.get('month')}")
    lines.append("")
    lines.append(f"Bundle ID: {manifest.get('month_bundle_id')}")
    lines.append(f"Entries: {manifest.get('count')}")
    lines.append("")

    for idx, entry in enumerate(manifest.get("entries", []), start=1):
        lines.append(f"## {idx}. {entry.get('title')} ({entry.get('day')})")
        lines.append("")
        lines.append(f"- Content ID: {entry.get('content_id')}")
        lines.append(f"- Episode ID: {entry.get('episode_id')}")
        lines.append(f"- Category: {entry.get('category')}")
        lines.append(f"- Angle: {entry.get('angle')}")
        lines.append(f"- Voice: {entry.get('voice')}")
        lines.append("")
        lines.append("### Hook")
        lines.append(entry.get("hook") or "")
        lines.append("")
        lines.append("### Body")
        lines.append(entry.get("body") or "")
        lines.append("")
        lines.append("### CTA")
        lines.append(entry.get("cta") or "")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def write_assets_csv(out_path: str, manifest: dict):
    fields = [
        "month",
        "month_bundle_id",
        "day",
        "content_id",
        "episode_id",
        "title",
        "category",
        "angle",
        "segment",
        "segment_id",
        "voice_track_id",
        "visual_asset_id",
    ]

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for entry in manifest.get("entries", []):
            segments = entry.get("segments") or {}
            for segment_name in ("hook", "body", "cta"):
                seg = segment_record(entry, segment_name, segments.get(segment_name))
                writer.writerow(
                    {
                        "month": manifest.get("month"),
                        "month_bundle_id": manifest.get("month_bundle_id"),
                        "day": entry.get("day"),
                        "content_id": entry.get("content_id"),
                        "episode_id": entry.get("episode_id"),
                        "title": entry.get("title"),
                        "category": entry.get("category"),
                        "angle": entry.get("angle"),
                        "segment": segment_name,
                        "segment_id": seg.get("segment_id"),
                        "voice_track_id": seg.get("voice_track_id"),
                        "visual_asset_id": seg.get("visual_asset_id"),
                    }
                )


def main():
    args = parse_args()
    month = args.month
    manifest_path = args.manifest or manifest_path_for_month(month)

    if not os.path.exists(manifest_path):
        raise SystemExit(f"ERROR: manifest not found: {manifest_path}")

    manifest = load_json(manifest_path)
    out_dir = os.path.join(MONTHLY_ROOT, month, "zine_pack")
    os.makedirs(out_dir, exist_ok=True)

    content_md = os.path.join(out_dir, "content.md")
    assets_csv = os.path.join(out_dir, "assets.csv")

    write_content_md(content_md, manifest)
    write_assets_csv(assets_csv, manifest)

    print(content_md)
    print(assets_csv)


if __name__ == "__main__":
    main()
