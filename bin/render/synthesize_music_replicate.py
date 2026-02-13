#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from urllib import request, error


def clean(value: str) -> str:
    return " ".join((value or "").strip().split())


def build_prompt(atom: dict) -> str:
    category = clean(atom.get("category") or "")
    angle = clean(atom.get("angle") or "")
    fact = atom.get("fact") or {}
    name = clean(fact.get("name") or "")
    style = atom.get("style") or {}
    tone = clean(style.get("tone") or "neutral")

    tone_map = {
        "gritty": "dark tactical fantasy underscore, tense, low percussion",
        "heroic": "uplifting fantasy adventure underscore, cinematic but light",
        "neutral": "clean tabletop fantasy underscore, subtle and steady",
    }
    tone_desc = tone_map.get(tone, tone_map["neutral"])

    parts = [
        tone_desc,
        "instrumental only, no vocals",
        "loop-friendly, non-distracting, creator-safe background music",
        f"theme: {category}",
    ]
    if angle:
        parts.append(f"angle: {angle}")
    if name:
        parts.append(f"subject: {name}")

    return "; ".join(parts)


def http_json(method: str, url: str, token: str, payload=None, timeout=90):
    data = None
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def download_file(url: str, out_path: str, timeout=180):
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        blob = resp.read()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(blob)


def extract_output_url(pred: dict) -> str:
    out = pred.get("output")
    if isinstance(out, str) and out.startswith("http"):
        return out
    if isinstance(out, list):
        for item in out:
            if isinstance(item, str) and item.startswith("http"):
                return item
            if isinstance(item, dict):
                url = item.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    return url
    if isinstance(out, dict):
        url = out.get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI background music via Replicate")
    parser.add_argument("--atom", required=True, help="Validated atom JSON path")
    parser.add_argument("--out", required=True, help="Output audio path")
    parser.add_argument("--duration", type=int, default=30, help="Target duration seconds")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt and payload only")
    args = parser.parse_args()

    token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    if not token and not args.dry_run:
        print("[music] ERROR: missing REPLICATE_API_TOKEN", file=sys.stderr)
        return 2

    with open(args.atom, "r", encoding="utf-8") as handle:
        atom = json.load(handle)

    prompt = build_prompt(atom)
    model = os.getenv("BIZZAL_REPLICATE_MUSIC_MODEL", "meta/musicgen")
    version = os.getenv("BIZZAL_REPLICATE_MUSIC_VERSION", "").strip()
    timeout_sec = int(os.getenv("BIZZAL_REPLICATE_MUSIC_TIMEOUT_SEC", "300"))

    input_payload = {
        "prompt": prompt,
        "duration": args.duration,
    }

    # Compatibility hints for common music models.
    input_payload.setdefault("seconds", args.duration)
    input_payload.setdefault("output_format", "wav")

    body = {
        "input": input_payload,
    }
    if version:
        body["version"] = version
    else:
        body["model"] = model

    if args.dry_run:
        print(json.dumps({"model": model, "version": version or None, "body": body}, indent=2, ensure_ascii=False))
        return 0

    try:
        pred = http_json("POST", "https://api.replicate.com/v1/predictions", token, body, timeout=90)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[music] ERROR: create prediction HTTP {exc.code}: {detail}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[music] ERROR: create prediction failed: {exc}", file=sys.stderr)
        return 4

    pred_id = pred.get("id")
    if not pred_id:
        print("[music] ERROR: prediction id missing", file=sys.stderr)
        return 5

    started = time.time()
    url = f"https://api.replicate.com/v1/predictions/{pred_id}"
    status = pred.get("status")
    while status not in {"succeeded", "failed", "canceled"}:
        if time.time() - started > timeout_sec:
            print("[music] ERROR: prediction timed out", file=sys.stderr)
            return 6
        time.sleep(2.0)
        try:
            pred = http_json("GET", url, token, None, timeout=60)
            status = pred.get("status")
        except Exception as exc:
            print(f"[music] ERROR: polling failed: {exc}", file=sys.stderr)
            return 7

    if status != "succeeded":
        print(f"[music] ERROR: prediction status={status}", file=sys.stderr)
        err = pred.get("error")
        if err:
            print(f"[music] details: {err}", file=sys.stderr)
        return 8

    out_url = extract_output_url(pred)
    if not out_url:
        print("[music] ERROR: no output URL in prediction", file=sys.stderr)
        return 9

    try:
        download_file(out_url, args.out, timeout=240)
    except Exception as exc:
        print(f"[music] ERROR: download failed: {exc}", file=sys.stderr)
        return 10

    print(f"[music] wrote {args.out} model={model} status={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
