#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from urllib import request, error


def looks_like_placeholder_key(value: str) -> bool:
    if not value:
        return True
    text = value.strip()
    markers = ["YOUR_OPENAI_API_KEY", "REPLACE_ME", "PASTE", "sk-xxxxx"]
    upper = text.upper()
    return any(marker in upper for marker in markers)


def clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    return text


def build_narration(atom: dict) -> str:
    script = atom.get("script") or {}
    hook = clean_text(script.get("hook") or "")
    body = clean_text(script.get("body") or "")
    cta = clean_text(script.get("cta") or "")

    parts = [p for p in [hook, body, cta] if p]
    return " ... ".join(parts)


def resolve_voice(atom: dict, voice_override: str) -> str:
    if voice_override:
        return voice_override
    style = atom.get("style") or {}
    voiceover = style.get("voiceover") or {}
    return (voiceover.get("tts_voice_id") or "alloy").strip() or "alloy"


def resolve_speed(speed_raw: str) -> float:
    try:
        speed = float((speed_raw or "1.0").strip())
    except Exception:
        speed = 1.0
    if speed < 0.25:
        speed = 0.25
    if speed > 4.0:
        speed = 4.0
    return speed


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize narration audio from a validated atom script.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--atom", help="Path to validated atom JSON")
    source.add_argument("--text", help="Direct narration text")
    source.add_argument("--text-file", help="Path to text file to narrate")
    parser.add_argument("--out", required=True, help="Output WAV path")
    parser.add_argument("--voice", default="", help="Optional explicit TTS voice override")
    parser.add_argument("--speed", default=os.getenv("BIZZAL_TTS_SPEED", "1.0"), help="TTS speaking speed (0.25-4.0)")
    parser.add_argument("--model", default=os.getenv("BIZZAL_TTS_MODEL", "gpt-4o-mini-tts"), help="OpenAI TTS model")
    parser.add_argument("--endpoint", default=os.getenv("BIZZAL_OPENAI_TTS_ENDPOINT", "https://api.openai.com/v1/audio/speech"), help="OpenAI TTS endpoint")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved payload details without calling API")
    args = parser.parse_args()

    atom = None
    if args.atom:
        with open(args.atom, "r", encoding="utf-8") as handle:
            atom = json.load(handle)
        narration = build_narration(atom)
    elif args.text is not None:
        narration = clean_text(args.text)
    else:
        with open(args.text_file, "r", encoding="utf-8") as handle:
            narration = clean_text(handle.read())

    if not narration:
        print("[tts] ERROR: narration text is empty", file=sys.stderr)
        return 2

    voice = resolve_voice(atom or {}, args.voice)
    speed = resolve_speed(args.speed)
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BIZZAL_OPENAI_API_KEY")

    if args.dry_run:
        print(f"[tts] dry-run model={args.model} voice={voice} speed={speed:.2f} chars={len(narration)}")
        print(f"[tts] out={args.out}")
        return 0

    if not api_key or looks_like_placeholder_key(api_key):
        print("[tts] ERROR: missing valid OPENAI_API_KEY/BIZZAL_OPENAI_API_KEY", file=sys.stderr)
        return 3

    payload = {
        "model": args.model,
        "voice": voice,
        "speed": speed,
        "input": narration,
        "response_format": "wav",
        "format": "wav",
    }

    req = request.Request(
        args.endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=90) as resp:
            audio = resp.read()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"[tts] ERROR: HTTP {exc.code}: {body}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"[tts] ERROR: request failed: {exc}", file=sys.stderr)
        return 5

    if not audio:
        print("[tts] ERROR: empty audio payload", file=sys.stderr)
        return 6

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as handle:
        handle.write(audio)

    print(f"[tts] wrote {args.out} voice={voice} speed={speed:.2f} chars={len(narration)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
