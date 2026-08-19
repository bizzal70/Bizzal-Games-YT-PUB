#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from urllib import request, error


def clean(value: str) -> str:
    return " ".join((value or "").strip().split())


def content_profile(atom: dict) -> str:
    label = clean(os.getenv("BIZZAL_CHAIN_LABEL") or "").lower()
    if label in {"shadowdark", "sd"}:
        return "shadowdark"

    source = atom.get("source") or {}
    active_srd_path = clean(source.get("active_srd_path") or "").lower()
    if "shadowdark" in active_srd_path:
        return "shadowdark"

    fact = atom.get("fact") or {}
    document = clean(fact.get("document") or "").lower()
    if "shadowdark" in document:
        return "shadowdark"

    return "dnd"


# ---------------------------------------------------------------------------
# Visual style presets — selected by BIZZAL_BG_STYLE env var.
# Add new entries here to introduce additional looks without touching logic.
# ---------------------------------------------------------------------------
_STYLE_PRESETS: dict[str, dict] = {
    # Stark black-and-white pen-and-ink illustration with a wry RTFM edge.
    # Think 1st-edition Monster Manual meets sardonic instructional diagram.
    "bw_rtfm": {
        "base": (
            "stark black and white pen-and-ink illustration, "
            "classic fantasy adventure art, bold confident linework, "
            "crosshatch shading, dramatic composition, "
            "no color, pure monochrome, black ink on white, "
            "no text anywhere, no letters, no numbers, no labels, no runes, no symbols"
        ),
        "tone_map": {
            "gritty":  "grim pen-and-ink scene, heavy crosshatch, oppressive negative space",
            "heroic":  "bold heroic diagram, clean ink lines, dramatic silhouette",
            "ominous": "ominous etching, dense shadow hatching, sinister vignette",
            "neutral": "clear instructional illustration, even linework, dry wit implied",
        },
        "category_map": {
            "monster_tactic":    "creature encounter scene, dramatic action, no text",
            "encounter_seed":    "encounter scene with adventurers, atmospheric, no text",
            "spell_use_case":    "arcane magic effect, dynamic energy, no text",
            "item_spotlight":    "fantasy artifact close-up, detailed linework, no text",
            "rules_ruling":      "adventurers in action, clear composition, no text",
            "rules_myth":        "dramatic fantasy scene, bold linework, no text",
            "character_micro_tip": "character in action pose, confident linework, no text",
        },
        "profile_shadowdark": (
            "old-school OSR dungeon crawl etching, "
            "harsh torch-shadow crosshatch, low-magic grim practicality"
        ),
        "shared_tail": [
            "no color, no grey washes, monochrome only",
            "absolutely no text, no letters, no numbers, no words, no labels, no runes, no glyphs, no symbols, no logos, no watermarks, no UI, no frame border",
        ],
    },

    # Current default: rich cinematic fantasy color art.
    "color_cinematic": {
        "base": "vertical 9:16 background image for short-form video",
        "tone_map": {
            "gritty":  "dark gritty fantasy art, moody contrast, weathered textures, cinematic shadows",
            "heroic":  "epic heroic fantasy art, cinematic composition, dramatic rim lighting, high grandeur",
            "ominous": "ominous dark fantasy art, torchlit gloom, high tension atmosphere, severe shadows",
            "neutral": "clean detailed fantasy art, balanced lighting, rich environment detail",
        },
        "category_map": {
            "monster_tactic":    "a dangerous creature encounter setup with tactical terrain",
            "encounter_seed":    "a game-ready fantasy encounter scene with clear visual stakes",
            "spell_use_case":    "an arcane spell moment with magical energy and dramatic motion",
            "item_spotlight":    "a close cinematic presentation of a fantasy artifact in its environment",
            "rules_ruling":      "a fantasy adventuring scene showing positional play and clarity",
            "rules_myth":        "a fantasy tabletop-inspired scene correcting a common tactical misconception",
            "character_micro_tip": "a class-focused fantasy moment showing role and decision-making",
        },
        "profile_shadowdark": (
            "old-school dark fantasy, torchlit dungeon mood, "
            "low-magic peril, claustrophobic ruins, grim practical adventuring tone"
        ),
        "shared_tail": [
            "high detail, atmospheric depth, tasteful depth of field",
            "no text, no logo, no watermark, no UI, no frame border",
            "no modern city, no firearms, no sci-fi tech",
        ],
    },
}

_STYLE_ORDER = list(_STYLE_PRESETS.keys())


def resolve_bg_style() -> str:
    """Return the active style key from BIZZAL_BG_STYLE, defaulting to bw_rtfm."""
    raw = clean(os.getenv("BIZZAL_BG_STYLE") or "").lower()
    if raw == "random":
        import random as _random
        return _random.choice(_STYLE_ORDER)
    return raw if raw in _STYLE_PRESETS else "bw_rtfm"


def build_prompt(atom: dict) -> str:
    category = clean(atom.get("category") or "")
    angle = clean(atom.get("angle") or "")
    style = atom.get("style") or {}
    tone = clean(style.get("tone") or "neutral")
    fact = atom.get("fact") or {}
    name = clean(fact.get("name") or "")
    kind = clean(fact.get("kind") or "")
    profile = content_profile(atom)
    chain_prefix = clean(os.getenv("BIZZAL_BG_IMAGE_PROMPT_PREFIX") or "")
    chain_suffix = clean(os.getenv("BIZZAL_BG_IMAGE_PROMPT_SUFFIX") or "")

    preset_key = resolve_bg_style()
    preset = _STYLE_PRESETS[preset_key]

    tone_desc = preset["tone_map"].get(tone, next(iter(preset["tone_map"].values())))
    scene_desc = preset["category_map"].get(category, "a tabletop RPG-inspired scene")

    parts = ["vertical 9:16 background image for short-form video", preset["base"]]
    if chain_prefix:
        parts.append(chain_prefix)
    if profile == "shadowdark":
        parts.append(preset["profile_shadowdark"])
    parts.extend([tone_desc, scene_desc])
    if name:
        label = kind or "subject"
        parts.append(f"focus on {label}: {name}")
    if angle:
        parts.append(f"angle emphasis: {angle}")
    parts.extend(preset["shared_tail"])
    if profile == "shadowdark" and preset_key == "color_cinematic":
        parts.append("avoid glossy high-fantasy sheen; emphasize darkness, stone, torch smoke, worn materials")
    if chain_suffix:
        parts.append(chain_suffix)

    print(f"[bgimg] style={preset_key}", file=sys.stderr)
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
    # Do NOT pass script text to the image model — Flux renders words as literal text in the image.
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
            # Retry on rate-limit (429) AND transient server errors (5xx) --
            # a 500 on submit is a Replicate hiccup, not a bad request.
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if retryable and attempt < max(1, attempts):
                wait_sec = 12
                try:
                    parsed = json.loads(detail)
                    wait_sec = int(parsed.get("retry_after") or wait_sec)
                except Exception:
                    pass
                wait_sec = max(3, min(60, wait_sec))
                print(f"[bgimg] create {exc.code} model={model_slug}; retrying in {wait_sec}s ({attempt}/{attempts})", file=sys.stderr)
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


_ANATOMY_SYSTEM = (
    "You are a strict QA checker for AI-generated fantasy illustration used as "
    "short-video backgrounds. Flag ONLY severe structural/anatomical defects that "
    "make a figure look broken: a human or creature clearly missing its head or "
    "face when it should have one, extra or missing limbs, fused or duplicated "
    "bodies, melted or grossly distorted faces, disconnected floating body parts, "
    "or impossible anatomy. Do NOT flag intentional stylistic choices: hooded, "
    "cloaked, masked or silhouetted figures, faces turned away or in shadow, figures "
    "cropped by the frame edge, abstract shapes, or creatures that naturally have no "
    "head. When unsure, do NOT flag. Respond with JSON only: "
    '{"defect": true|false, "severity": "none|minor|severe", "issues": ["short reason"]}'
)


def detect_structural_defects(path: str) -> tuple[bool, list[str], str]:
    """Vision QA gate for anatomy/structure defects (headless figures, extra limbs,
    melted faces). Only SEVERE defects reject. Returns (has_severe, issues, status)
    with status in {ok, disabled, no_key, error}. Never blocks rendering: any
    failure returns (False, [], status) so a QA outage can't stop the pipeline.
    """
    if os.getenv("BIZZAL_BG_IMAGE_ANATOMY_CHECK", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return False, [], "disabled"
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BIZZAL_OPENAI_API_KEY")
    if not api_key:
        return False, [], "no_key"
    model = os.getenv("BIZZAL_BG_IMAGE_VISION_MODEL", "gpt-4o-mini")
    try:
        with open(path, "rb") as handle:
            b64 = base64.b64encode(handle.read()).decode("ascii")
    except Exception:
        return False, [], "error"
    fmt = "png" if path.lower().endswith(".png") else "jpeg"
    payload = {
        "model": model,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": _ANATOMY_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": "Check this background image for severe structural defects."},
                {"type": "image_url", "image_url": {"url": f"data:image/{fmt};base64,{b64}"}},
            ]},
        ],
    }
    try:
        req = request.Request(
            os.getenv("BIZZAL_OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as resp:
            content = (((json.loads(resp.read().decode("utf-8")).get("choices") or [{}])[0]
                        ).get("message") or {}).get("content") or "{}"
    except Exception as exc:
        print(f"[bgimg] WARN: anatomy check failed: {exc}", file=sys.stderr)
        return False, [], "error"
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip()
    try:
        verdict = json.loads(raw)
    except Exception:
        return False, [], "error"
    severe = bool(verdict.get("defect")) and str(verdict.get("severity", "")).lower() == "severe"
    return severe, (verdict.get("issues") or []), "ok"


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
    poll_errs = 0
    max_poll_errs = int(os.getenv("BIZZAL_REPLICATE_POLL_MAX_ERRORS", "30"))
    while status not in {"succeeded", "failed", "canceled"}:
        if time.time() - started > timeout_sec:
            return None, "prediction timed out"
        time.sleep(2.0)
        try:
            pred = http_json("GET", url, token, None, timeout=60)
            status = pred.get("status")
            poll_errs = 0
        except Exception as exc:
            # A 500 on the STATUS poll does NOT mean the image failed -- the
            # prediction is still running server-side. Abandoning it here was
            # the main cause of long-form losing an image and tripping the
            # render quality gate. Keep re-polling the same prediction (with
            # growing backoff, bounded by timeout_sec) instead of giving up.
            poll_errs += 1
            if poll_errs >= max_poll_errs:
                return None, f"polling failed {poll_errs}x: {exc}"
            time.sleep(min(15, 2 * poll_errs))

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

    attempts = int(os.getenv("BIZZAL_REPLICATE_IMAGE_CREATE_ATTEMPTS", "4"))
    timeout_sec = int(os.getenv("BIZZAL_REPLICATE_IMAGE_TIMEOUT_SEC", "300"))
    # More whole-prediction attempts to outlast an intermittent Replicate wobble
    # (each failed image otherwise trips the render's per-screen quality gate).
    candidate_attempts = int(os.getenv("BIZZAL_BG_IMAGE_CANDIDATE_ATTEMPTS", "6"))
    ocr_unavailable_warned = False
    anatomy_unavailable_warned = False

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
            # A prediction that fails MID-EXECUTION (e.g. Replicate E9828
            # "Director: unexpected error handling prediction") is transient --
            # retry with a fresh prediction on the next candidate attempt rather
            # than giving up, which would trip the render quality gate and skip
            # the whole upload. Previously this returned immediately (0 retries).
            print(
                f"[bgimg] WARN: prediction failed ({wait_err}); "
                f"retry {candidate_idx + 1}/{candidate_attempts}",
                file=sys.stderr,
            )
            if candidate_idx < candidate_attempts - 1:
                time.sleep(min(30, 5 + candidate_idx * 4))
                continue
            print(
                f"[bgimg] ERROR: all {candidate_attempts} prediction attempts failed; "
                f"last={wait_err}",
                file=sys.stderr,
            )
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

        # Vision anatomy/structure QA — only when text-clean (saves a call on
        # candidates already being rejected for text).
        has_defect, defect_issues, defect_status = (False, [], "skip")
        if not has_text:
            has_defect, defect_issues, defect_status = detect_structural_defects(tmp_out)
            if defect_status == "no_key" and not anatomy_unavailable_warned:
                print("[bgimg] WARN: no OpenAI key; skipping anatomy QA gate", file=sys.stderr)
                anatomy_unavailable_warned = True

        if (has_text or has_defect) and candidate_idx < candidate_attempts - 1:
            if has_text:
                reason = f"detected_text_tokens={','.join(tokens[:6]) if tokens else 'n/a'}"
            else:
                reason = f"structural_defect={'; '.join(defect_issues[:2]) or 'severe'}"
            print(
                f"[bgimg] reject candidate={candidate_idx + 1}/{candidate_attempts} {reason}; regenerating",
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
        if has_defect:
            print(
                f"[bgimg] WARN: accepted final candidate with structural issues={'; '.join(defect_issues[:2]) or 'severe'}",
                file=sys.stderr,
            )

        print(f"[bgimg] wrote {args.out} model={used_model} status=succeeded candidate={candidate_idx + 1}")
        return 0

    print("[bgimg] ERROR: exhausted candidate generation attempts", file=sys.stderr)
    return 11


if __name__ == "__main__":
    raise SystemExit(main())
