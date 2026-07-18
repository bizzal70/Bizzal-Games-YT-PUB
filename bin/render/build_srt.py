#!/usr/bin/env python3
"""
build_srt.py -- emit a SubRip (.srt) caption track for a rendered video.

The renderer narrates one TTS segment per screen (hook, body pages, cta) and
concatenates them GAPLESSLY into the voice track. So the spoken timeline is the
running sum of the real per-segment audio durations -- NOT the padded on-screen
SCREEN_SECS. Captioning off the audio durations keeps CC locked to speech.

Input: a manifest file, one cue per line, TAB-separated:
    <segment_wav_or_duration_seconds>\t<text_file>
where the first field is either a path to the segment .wav (its duration is
probed) or a bare float duration. Blank text files are skipped (no cue).

Usage:
    build_srt.py --manifest plan.tsv --out DAY.srt [--offset 0]
        [--min-cue-sec 1.2]

--offset shifts every cue later by N seconds (leading intro-pad silence).
--min-cue-sec guarantees a readable floor if a probed segment is tiny.
"""
import argparse
import pathlib
import subprocess
import sys


def probe_duration(path: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        text=True,
    ).strip()
    return float(out)


def resolve_duration(field: str) -> float:
    try:
        return float(field)
    except ValueError:
        return probe_duration(field)


def fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def collapse(text: str) -> str:
    # The page text is hard-wrapped at ~42 cols for the video overlay; CC should
    # be a single logical line and let the player re-wrap it.
    return " ".join(text.split())


def build(manifest_lines, offset=0.0, min_cue_sec=1.2):
    """Return SRT text. Pure function over (duration, text) rows for testing."""
    cues = []
    t = float(offset)
    for raw in manifest_lines:
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        dur_field, _, text_field = raw.partition("\t")
        dur = resolve_duration(dur_field.strip())
        text = collapse(pathlib.Path(text_field).read_text(encoding="utf-8")
                        if text_field and pathlib.Path(text_field).exists()
                        else text_field)
        start = t
        end = t + max(dur, min_cue_sec)
        t += dur  # advance by REAL duration, not the padded floor
        if text:
            cues.append((start, end, text))
    blocks = []
    for i, (start, end, text) in enumerate(cues, start=1):
        blocks.append(f"{i}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n")
    return "\n".join(blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--min-cue-sec", type=float, default=1.2)
    args = ap.parse_args()

    lines = pathlib.Path(args.manifest).read_text(encoding="utf-8").splitlines()
    srt = build(lines, offset=args.offset, min_cue_sec=args.min_cue_sec)
    if not srt.strip():
        print("[build_srt] no cues; skipping", file=sys.stderr)
        return
    pathlib.Path(args.out).write_text(srt + "\n", encoding="utf-8")
    n = srt.count(" --> ")
    print(f"[build_srt] wrote {args.out} ({n} cues)")


if __name__ == "__main__":
    main()
