#!/usr/bin/env python3
import argparse, pathlib

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--prefix", default="page")
    ap.add_argument("--maxlines", type=int, default=9)
    args = ap.parse_args()

    s = pathlib.Path(args.infile).read_text(encoding="utf-8").rstrip("\n")
    lines = s.splitlines()
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    pages = []
    for i in range(0, len(lines), args.maxlines):
        chunk = lines[i:i+args.maxlines]
        pages.append("\n".join(chunk).strip())

    if not pages:
        pages = [""]

    for idx, txt in enumerate(pages, start=1):
        (outdir / f"{args.prefix}{idx}.txt").write_text(txt + "\n", encoding="utf-8")

    print(len(pages))

if __name__ == "__main__":
    main()
