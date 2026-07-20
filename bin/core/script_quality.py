#!/usr/bin/env python3
"""
script_quality.py -- editorial gate: judge a generated script BEFORE it renders.

The pipeline had only technical gates ("did Replicate return an image"), so a
weak script became a video regardless of quality. This scores the script against
the channel's RTFM voice and lets the caller regenerate instead of publish.

Contract for callers:
    verdict = judge(script_text, context="D&D 5e long-form")
    verdict.score      float 1-5
    verdict.issues     list[str]
    verdict.ok         score >= target
    verdict.publishable score >= floor  (below floor => do NOT publish)
    verdict.available  False if the judge could not run (fail-OPEN: treat as ok)

Env:
    BIZZAL_OPENAI_API_KEY          required to actually judge (else fail-open)
    BIZZAL_SCRIPT_QUALITY_GATE     "0" disables the gate entirely
    BIZZAL_SCRIPT_QUALITY_TARGET   default 4.0  (below -> regenerate)
    BIZZAL_SCRIPT_QUALITY_FLOOR    default 3.0  (below -> block publish)
    BIZZAL_SCRIPT_QUALITY_MODEL    default gpt-4o
"""
import json
import os
from dataclasses import dataclass, field
from urllib import request

TARGET = float(os.environ.get("BIZZAL_SCRIPT_QUALITY_TARGET", "4.0"))
FLOOR = float(os.environ.get("BIZZAL_SCRIPT_QUALITY_FLOOR", "3.0"))
MODEL = os.environ.get("BIZZAL_SCRIPT_QUALITY_MODEL", "gpt-4o")


def gate_enabled() -> bool:
    return (os.environ.get("BIZZAL_SCRIPT_QUALITY_GATE") or "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


@dataclass
class Verdict:
    score: float = 5.0
    issues: list = field(default_factory=list)
    available: bool = True
    raw: str = ""

    @property
    def ok(self) -> bool:
        return (not self.available) or self.score >= TARGET

    @property
    def publishable(self) -> bool:
        return (not self.available) or self.score >= FLOOR


_PROMPT = """You are the editor-in-chief for Bizzal Games, a tabletop RPG channel.

House voice (RTFM): dry, factual, wry. EVERY sentence must carry a specific
mechanic, number, condition, or ruling. Banned: theatrical openers, "picture
this", hype adjectives, generic GM advice, filler, padding, repetition.

Context: {context}

SCRIPT:
{script}

Score the script 1-5 (decimals allowed) weighing:
- specificity: does each claim cite a concrete mechanic/number/condition?
- density: zero filler, padding, or repeated points
- voice: dry and factual, NOT hype or vague advice
- usefulness: would a player/GM actually change how they play?

Be a harsh editor. A script that is merely competent and generic is a 3.
A script where every line teaches a concrete ruling is a 5.

Return ONLY JSON, no markdown:
{{"score": <number>, "issues": ["short issue", "..."]}}"""


def _call(prompt: str, api_key: str, timeout: int = 60) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 500,
    }).encode("utf-8")
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def parse_verdict(raw: str) -> Verdict:
    """Tolerant parse of the judge's JSON (fenced / prose-wrapped tolerated)."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = "\n".join(s.split("\n")[1:])
    if s.endswith("```"):
        s = "\n".join(s.split("\n")[:-1])
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b > a:
        s = s[a:b + 1]
    try:
        d = json.loads(s)
    except Exception:
        return Verdict(score=5.0, issues=[], available=False, raw=raw)
    try:
        score = float(d.get("score"))
    except Exception:
        return Verdict(score=5.0, issues=[], available=False, raw=raw)
    issues = [str(i) for i in (d.get("issues") or [])][:6]
    return Verdict(score=score, issues=issues, available=True, raw=raw)


def judge(script_text: str, context: str = "") -> Verdict:
    """Score a script. Fail-OPEN: any problem returns available=False (=> ok)."""
    if not gate_enabled():
        return Verdict(available=False)
    api_key = os.environ.get("BIZZAL_OPENAI_API_KEY", "")
    if not api_key or not (script_text or "").strip():
        return Verdict(available=False)
    try:
        raw = _call(_PROMPT.format(context=context or "n/a", script=script_text[:12000]), api_key)
    except Exception:
        return Verdict(available=False)
    return parse_verdict(raw)


if __name__ == "__main__":
    import sys
    txt = sys.stdin.read()
    v = judge(txt, context=" ".join(sys.argv[1:]))
    print(json.dumps({
        "score": v.score, "issues": v.issues, "available": v.available,
        "ok(>=%.1f)" % TARGET: v.ok, "publishable(>=%.1f)" % FLOOR: v.publishable,
    }, indent=2))
