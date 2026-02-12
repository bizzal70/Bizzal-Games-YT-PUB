#!/usr/bin/env python3
import argparse, pathlib, textwrap

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--width", type=int, default=42)
    args = ap.parse_args()

    s = pathlib.Path(args.inp).read_text(encoding="utf-8").strip()
    # Preserve blank lines if any, wrap each paragraph
    parts = [p.strip() for p in s.split("\n\n")]
    wrapped = []
    for p in parts:
        if not p:
            wrapped.append("")
            continue
        wrapped.append(textwrap.fill(p, width=args.width, break_long_words=False, break_on_hyphens=False))
    pathlib.Path(args.out).write_text("\n\n".join(wrapped) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
