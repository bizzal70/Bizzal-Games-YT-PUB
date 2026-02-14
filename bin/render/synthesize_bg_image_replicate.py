#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
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


def build_section_prompt(base_prompt: str, section: str, section_text: str) -> str:
    section_key = clean(section or "").lower()
    section_line = clean(section_text or "")
    if len(section_line) > 220:
        section_line = section_line[:220].rsplit(" ", 1)[0] + "..."

    section_map = {
        "hook": "opening beat, immediate visual hook, dramatic composition",
        "body": "main tactical scene with clear spatial storytelling",
        "cta": "closing beat, resolved composition, dramatic aftermath",
    }
    section_desc = section_map.get(section_key, "cohesive scene continuation")

    parts = [base_prompt, f"screen phase: {section_desc}"]
    if section_line:
        parts.append(f"visual cue from script: {section_line}")
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


def tokenize_ocr_text(raw: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]{1,}", raw or "")
    cleaned = []
    for tok in tokens:
        t = tok.strip().lower()
        if len(t) < 2:
            continue
        cleaned.append(t)
    return cleaned


def detect_visible_text(path: str) -> tuple[bool, list[str], str]:
    """
    Returns:
      (has_text, tokens, status)
      status in {"ok", "no_tesseract", "ocr_error"}
    """
    if (os.getenv("BIZZAL_BG_IMAGE_OCR_ENABLED", "1").strip().lower() not in {"1", "true", "yes", "on"}):
        return False, [], "ok"

    psm = (os.getenv("BIZZAL_BG_IMAGE_OCR_PSM", "11").strip() or "11")
    language = (os.getenv("BIZZAL_BG_IMAGE_OCR_LANG", "eng").strip() or "eng")
    min_tokens = int(os.getenv("BIZZAL_BG_IMAGE_OCR_MIN_TOKENS", "2"))

    try:
        proc = subprocess.run(
            ["tesseract", path, "stdout", "--psm", psm, "-l", language],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, [], "no_tesseract"
    except Exception:
        return False, [], "ocr_error"

    if proc.returncode != 0:
        return False, [], "ocr_error"

    tokens = tokenize_ocr_text(proc.stdout)
    return (len(tokens) >= max(1, min_tokens)), tokens, "ok"


def enrich_prompt(base_prompt: str, attempt_index: int) -> str:
    anti_text = (
        "absolutely no readable text anywhere, no letters, no numbers, "
        "no words, no typography, no runes, no signage, no UI"
    )
    attempt_flavors = [
        "clean cinematic composition",
        "organic environmental details only",
        "painterly matte-art style, no glyph-like marks",
        "natural textures without symbols",
        "film still composition with clear non-text surfaces",
    ]
    flavor = attempt_flavors[attempt_index % len(attempt_flavors)]
    return f"{base_prompt}; {anti_text}; variation: {flavor}"


def create_prediction(token: str, deduped_models: list[str], payload_variants: list[dict], attempts: int):
    pred = None
    used_model = ""
    for model_slug in deduped_models:
        used_model = model_slug
        for payload in payload_variants:
            pred, err = post_prediction(token, model_slug, payload, attempts)
            if pred is not None:
                return pred, used_model, None
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
            return None, used_model, f"create prediction model={model_slug} HTTP {code}: {detail}"
    return None, used_model, None


def wait_for_prediction(token: str, pred: dict, timeout_sec: int):
    pred_id = pred.get("id")
    if not pred_id:
        return None, "prediction id missing"

    started = time.time()
    url = f"https://api.replicate.com/v1/predictions/{pred_id}"
    status = pred.get("status")
    while status not in {"succeeded", "failed", "canceled"}:
        if time.time() - started > timeout_sec:
            return None, "prediction timed out"
        time.sleep(2.0)
        try:
            pred = http_json("GET", url, token, None, timeout=60)
            status = pred.get("status")
        except Exception as exc:
            return None, f"polling failed: {exc}"

    if status != "succeeded":
        err = pred.get("error")
        if err:
            return None, f"prediction status={status} details={err}"
        return None, f"prediction status={status}"

    out_url = extract_output_url(pred)
    if not out_url:
        return None, "no output URL in prediction"
    return out_url, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI background image via Replicate")
    parser.add_argument("--atom", required=True, help="Validated atom JSON path")
    parser.add_argument("--out", required=True, help="Output image path")
    parser.add_argument("--section", default="", help="Optional screen section label (hook/body/cta)")
    parser.add_argument("--text-file", default="", help="Optional section script text path for prompt cue")
    parser.add_argument("--dry-run", action="store_true", help="Print chosen prompt and payloads")
    args = parser.parse_args()

    token = os.getenv("REPLICATE_API_TOKEN", "").strip()
    if not token and not args.dry_run:
        print("[bgimg] ERROR: missing REPLICATE_API_TOKEN", file=sys.stderr)
        return 2

    with open(args.atom, "r", encoding="utf-8") as handle:
        atom = json.load(handle)

    prompt = build_prompt(atom)
    if args.section or args.text_file:
        section_text = ""
        if args.text_file:
            try:
                with open(args.text_file, "r", encoding="utf-8") as handle:
                    section_text = handle.read()
            except Exception:
                section_text = ""
        prompt = build_section_prompt(prompt, args.section, section_text)
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
    timeout_sec = int(os.getenv("BIZZAL_REPLICATE_IMAGE_TIMEOUT_SEC", "300"))
    candidate_attempts = int(os.getenv("BIZZAL_BG_IMAGE_CANDIDATE_ATTEMPTS", "4"))
    ocr_unavailable_warned = False

    for candidate_idx in range(max(1, candidate_attempts)):
        candidate_prompt = enrich_prompt(prompt, candidate_idx)
        payload_variants = [
            {"input": {"prompt": candidate_prompt, "aspect_ratio": aspect_ratio, "output_format": output_format, "num_outputs": 1}},
            {"input": {"prompt": candidate_prompt, "aspect_ratio": aspect_ratio}},
            {"input": {"prompt": candidate_prompt}},
        ]

        pred, used_model, create_err = create_prediction(token, deduped_models, payload_variants, attempts)
        if pred is None:
            if create_err:
                print(f"[bgimg] ERROR: {create_err}", file=sys.stderr)
                return 3
            print("[bgimg] ERROR: no accessible image model/payload combination succeeded", file=sys.stderr)
            return 4

        out_url, wait_err = wait_for_prediction(token, pred, timeout_sec)
        if wait_err:
            print(f"[bgimg] ERROR: {wait_err}", file=sys.stderr)
            return 6

        try:
            tmp_out = args.out if candidate_idx == candidate_attempts - 1 else f"{args.out}.candidate{candidate_idx}.tmp"
            download_file(out_url, tmp_out, timeout=240)
        except Exception as exc:
            print(f"[bgimg] ERROR: download failed: {exc}", file=sys.stderr)
            return 10

        has_text, tokens, status = detect_visible_text(tmp_out)
        if status == "no_tesseract" and not ocr_unavailable_warned:
            print("[bgimg] WARN: tesseract not installed; cannot OCR-reject text artifacts", file=sys.stderr)
            ocr_unavailable_warned = True
        elif status == "ocr_error":
            print("[bgimg] WARN: OCR failed; accepting image without text gate", file=sys.stderr)

        if has_text and candidate_idx < candidate_attempts - 1:
            preview = ",".join(tokens[:6]) if tokens else "n/a"
            print(
                f"[bgimg] reject candidate={candidate_idx + 1}/{candidate_attempts} detected_text_tokens={preview}; regenerating",
                file=sys.stderr,
            )
            try:
                os.remove(tmp_out)
            except Exception:
                pass
            continue

        if tmp_out != args.out:
            os.replace(tmp_out, args.out)

        if has_text:
            preview = ",".join(tokens[:6]) if tokens else "n/a"
            print(
                f"[bgimg] WARN: accepted final candidate with detected text tokens={preview}",
                file=sys.stderr,
            )

        print(f"[bgimg] wrote {args.out} model={used_model} status=succeeded candidate={candidate_idx + 1}")
        return 0

    print("[bgimg] ERROR: exhausted candidate generation attempts", file=sys.stderr)
    return 11


if __name__ == "__main__":
    raise SystemExit(main())
