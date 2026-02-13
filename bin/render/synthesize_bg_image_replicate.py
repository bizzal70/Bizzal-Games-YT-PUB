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
    style = atom.get("style") or {}
    tone = clean(style.get("tone") or "neutral")
    fact = atom.get("fact") or {}
    name = clean(fact.get("name") or "")
    kind = clean(fact.get("kind") or "")

    tone_map = {
        "gritty": "dark gritty fantasy art, moody contrast, weathered textures, cinematic shadows",
        "heroic": "epic heroic fantasy art, cinematic composition, dramatic rim lighting, high grandeur",
        "neutral": "clean detailed fantasy art, balanced lighting, rich environment detail",
    }
    category_map = {
        "monster_tactic": "a dangerous creature encounter setup with tactical terrain",
        "encounter_seed": "a game-ready fantasy encounter scene with clear visual stakes",
        "spell_use_case": "an arcane spell moment with magical energy and dramatic motion",
        "item_spotlight": "a close cinematic presentation of a fantasy artifact in its environment",
        "rules_ruling": "a fantasy adventuring scene showing positional play and clarity",
        "rules_myth": "a fantasy tabletop-inspired scene correcting a common tactical misconception",
        "character_micro_tip": "a class-focused fantasy moment showing role and decision-making",
    }

    tone_desc = tone_map.get(tone, tone_map["neutral"])
    scene_desc = category_map.get(category, "a cinematic fantasy tabletop-inspired scene")

    parts = [
        "vertical 9:16 background image for short-form video",
        tone_desc,
        scene_desc,
    ]
    if name:
        label = kind or "subject"
        parts.append(f"focus on {label}: {name}")
    if angle:
        parts.append(f"angle emphasis: {angle}")

    parts.extend(
        [
            "high detail, atmospheric depth, tasteful depth of field",
            "no text, no logo, no watermark, no UI, no frame border",
            "no modern city, no firearms, no sci-fi tech",
        ]
    )
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


def post_prediction(token: str, model_slug: str, payload: dict, attempts: int):
    parts = [p for p in (model_slug or "").split("/") if p]
    if len(parts) != 2:
        raise ValueError(f"invalid model slug: {model_slug}")
    owner, name = parts
    url = f"https://api.replicate.com/v1/models/{owner}/{name}/predictions"

    for attempt in range(1, max(1, attempts) + 1):
        try:
            return http_json("POST", url, token, payload, timeout=90), None
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 429 and attempt < max(1, attempts):
                wait_sec = 12
                try:
                    parsed = json.loads(detail)
                    wait_sec = int(parsed.get("retry_after") or wait_sec)
                except Exception:
                    pass
                wait_sec = max(3, min(60, wait_sec))
                print(f"[bgimg] rate-limited model={model_slug}; retrying in {wait_sec}s ({attempt}/{attempts})", file=sys.stderr)
                time.sleep(wait_sec)
                continue
            return None, (exc.code, detail)
        except Exception as exc:
            return None, (0, str(exc))
    return None, (0, "exhausted retries")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI background image via Replicate")
    parser.add_argument("--atom", required=True, help="Validated atom JSON path")
    parser.add_argument("--out", required=True, help="Output image path")
    parser.add_argument("--dry-run", action="store_true", help="Print chosen prompt and payloads")
    args = parser.parse_args()

    token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    if not token and not args.dry_run:
        print("[bgimg] ERROR: missing REPLICATE_API_TOKEN", file=sys.stderr)
        return 2

    with open(args.atom, "r", encoding="utf-8") as handle:
        atom = json.load(handle)

    prompt = build_prompt(atom)
    aspect_ratio = os.getenv("BIZZAL_BG_IMAGE_ASPECT_RATIO", "9:16").strip() or "9:16"
    output_format = os.getenv("BIZZAL_BG_IMAGE_FORMAT", "png").strip() or "png"

    model_candidates = [
        m.strip()
        for m in (
            os.getenv("BIZZAL_REPLICATE_IMAGE_MODEL", "black-forest-labs/flux-schnell"),
            "black-forest-labs/flux-schnell",
            "black-forest-labs/flux-dev",
            "stability-ai/stable-diffusion-3.5-large",
        )
        if (m or "").strip()
    ]
    deduped_models = []
    for slug in model_candidates:
        if slug not in deduped_models:
            deduped_models.append(slug)

    payload_variants = [
        {"input": {"prompt": prompt, "aspect_ratio": aspect_ratio, "output_format": output_format, "num_outputs": 1}},
        {"input": {"prompt": prompt, "aspect_ratio": aspect_ratio}},
        {"input": {"prompt": prompt}},
    ]

    if args.dry_run:
        print(json.dumps({"models": deduped_models, "payloads": payload_variants}, indent=2, ensure_ascii=False))
        return 0

    attempts = int(os.getenv("BIZZAL_REPLICATE_IMAGE_CREATE_ATTEMPTS", "3"))
    pred = None
    used_model = ""

    for model_slug in deduped_models:
        used_model = model_slug
        for payload in payload_variants:
            pred, err = post_prediction(token, model_slug, payload, attempts)
            if pred is not None:
                break
            if not err:
                continue
            code, detail = err
            if code in {403, 404, 422}:
                if code == 422:
                    print(f"[bgimg] skip payload model={model_slug} HTTP 422", file=sys.stderr)
                else:
                    print(f"[bgimg] skip model={model_slug} HTTP {code}", file=sys.stderr)
                    break
                continue
            print(f"[bgimg] ERROR: create prediction model={model_slug} HTTP {code}: {detail}", file=sys.stderr)
            return 3
        if pred is not None:
            break

    if pred is None:
        print("[bgimg] ERROR: no accessible image model/payload combination succeeded", file=sys.stderr)
        return 4

    pred_id = pred.get("id")
    if not pred_id:
        print("[bgimg] ERROR: prediction id missing", file=sys.stderr)
        return 5

    timeout_sec = int(os.getenv("BIZZAL_REPLICATE_IMAGE_TIMEOUT_SEC", "300"))
    started = time.time()
    url = f"https://api.replicate.com/v1/predictions/{pred_id}"
    status = pred.get("status")
    while status not in {"succeeded", "failed", "canceled"}:
        if time.time() - started > timeout_sec:
            print("[bgimg] ERROR: prediction timed out", file=sys.stderr)
            return 6
        time.sleep(2.0)
        try:
            pred = http_json("GET", url, token, None, timeout=60)
            status = pred.get("status")
        except Exception as exc:
            print(f"[bgimg] ERROR: polling failed: {exc}", file=sys.stderr)
            return 7

    if status != "succeeded":
        print(f"[bgimg] ERROR: prediction status={status}", file=sys.stderr)
        err = pred.get("error")
        if err:
            print(f"[bgimg] details: {err}", file=sys.stderr)
        return 8

    out_url = extract_output_url(pred)
    if not out_url:
        print("[bgimg] ERROR: no output URL in prediction", file=sys.stderr)
        return 9

    try:
        download_file(out_url, args.out, timeout=240)
    except Exception as exc:
        print(f"[bgimg] ERROR: download failed: {exc}", file=sys.stderr)
        return 10

    print(f"[bgimg] wrote {args.out} model={used_model} status={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
