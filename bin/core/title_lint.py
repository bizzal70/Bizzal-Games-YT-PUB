#!/usr/bin/env python3
"""
title_lint.py -- editorial guard for published titles.

The channel's proven formula is: specific named subject + concrete, often
counterintuitive ruling ("Barrier Tattoo only works without armor"). Real
defects have shipped that this catches:

  "Low-threat on paper, high-chaos at the table • Hellseeker Cockatrice"
      -> bullet template artifact (descriptor-first, subject buried)
  "The Mirror Of Mischief creates an evil duplicate the"
      -> truncated mid-sentence, dangling article
  "Mechanics moment: Saving Throws and Damage"
      -> generic label prefix, no ruling, no specificity
  "Use Mastiff as 'comic relief' that quietly pressures"
      -> GM-advice voice instead of a ruling, and truncated

clean() fixes what is mechanically fixable; issues() reports what is not.
Callers treat HARD issues as "do not publish this title as-is".
"""
import re

MAX_LEN = 100

# Words a title must never end on -- a sign it was cut mid-thought.
_DANGLING = {
    "the", "a", "an", "of", "to", "with", "and", "or", "but", "that", "which",
    "for", "in", "on", "at", "by", "from", "as", "into", "than", "then",
    "when", "while", "is", "are", "was", "were", "be", "been", "its", "their",
}

# Generic label prefixes that carry no information.
_GENERIC_PREFIXES = (
    "mechanics moment", "light tone", "quick tip", "tip:", "note:",
    "did you know", "fun fact", "spotlight:", "breakdown:",
)

# Hype/clickbait patterns we deliberately moved away from.
_HYPE = ("unpacking ", "unlocking ", "ultimate ", "secrets of", "you won't believe")

# GM-advice framing ("Use X as...") instead of a ruling. Off-formula: the
# channel's winners state what the rules DO, not what the GM should do.
_ADVICE_STARTS = ("use ", "run ", "try ", "remember ", "consider ", "let ", "give ")

HARD = {"BULLET_ARTIFACT", "DANGLING_END", "GENERIC_PREFIX", "TOO_SHORT", "HYPE",
        "ADVICE_VOICE"}


def clean(title: str) -> str:
    """Mechanically repair what can be repaired. Never invents content."""
    t = " ".join((title or "").split())
    # Template artifact: "descriptor • Subject" -> lead with the Subject.
    if "•" in t:
        left, _, right = t.partition("•")
        left, right = left.strip(" -–—,:"), right.strip(" -–—,:")
        if right:
            t = f"{right}: {left}" if left else right
        else:
            t = left
    # Trailing punctuation noise, then dangling function words.
    t = t.strip(" -–—,:;")
    words = t.split()
    while words and re.sub(r"[^a-z]", "", words[-1].lower()) in _DANGLING:
        words.pop()
    t = " ".join(words).strip(" -–—,:;")
    return t[:MAX_LEN].strip()


def issues(title: str) -> list[str]:
    """Problems remaining in a title (run AFTER clean() for a true verdict)."""
    t = (title or "").strip()
    low = t.lower()
    out = []
    if "•" in t:
        out.append("BULLET_ARTIFACT")
    words = t.split()
    if words and re.sub(r"[^a-z]", "", words[-1].lower()) in _DANGLING:
        out.append("DANGLING_END")
    if any(low.startswith(p) for p in _GENERIC_PREFIXES):
        out.append("GENERIC_PREFIX")
    if any(h in low for h in _HYPE):
        out.append("HYPE")
    if any(low.startswith(a) for a in _ADVICE_STARTS):
        out.append("ADVICE_VOICE")
    if len(words) < 4:
        out.append("TOO_SHORT")
    return out


def is_publishable(title: str) -> bool:
    return not (set(issues(title)) & HARD)


def lint(title: str) -> tuple[str, list[str], bool]:
    """Return (cleaned_title, remaining_issues, publishable)."""
    c = clean(title)
    i = issues(c)
    return c, i, not (set(i) & HARD)


if __name__ == "__main__":
    import sys
    for raw in sys.argv[1:]:
        c, i, ok = lint(raw)
        print(f"{'OK ' if ok else 'BAD'}  {raw!r}\n     -> {c!r}  issues={i or 'none'}")
