#!/usr/bin/env python3
import argparse, pathlib, re, textwrap


def split_sentences(text: str):
    """Split flowing text into whole sentences, keeping the terminator.
    Breaks only on . ! ? … followed by whitespace (a colon keeps the clause
    together). Good enough for the clean RTFM prose we narrate."""
    parts = re.split(r'(?<=[.!?…])(?=\s)', text)
    return [p.strip() for p in parts if p.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--prefix", default="page")
    ap.add_argument("--maxlines", type=int, default=9)
    args = ap.parse_args()

    s = pathlib.Path(args.infile).read_text(encoding="utf-8").rstrip("\n")
    src_lines = s.splitlines()
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Sentence-aware pagination. Each page is fed to the TTS engine as its OWN
    # synthesis call, so a page ending mid-sentence makes the narration reset
    # its intonation on the next screen AND clip the trailing words of the
    # incomplete fragment. The caller wraps text to the frame first, which puts
    # sentence ends mid-line -- so we reconstruct the flowing text, split it into
    # whole sentences, pack sentences into pages of <= maxlines lines, and
    # re-wrap each page at the SAME inferred width (so the on-screen line layout
    # is unchanged; only the page boundaries move to sentence ends).
    width = max((len(ln) for ln in src_lines if ln.strip()), default=60)
    text = re.sub(r"\s+", " ", " ".join(ln.strip() for ln in src_lines)).strip()
    sentences = split_sentences(text) or ([text] if text else [""])

    def wrapped(t: str):
        return textwrap.wrap(t, width=width, break_long_words=False,
                             break_on_hyphens=False) or [""]

    pages, cur = [], ""
    for sent in sentences:
        cand = (cur + " " + sent).strip() if cur else sent
        if cur and len(wrapped(cand)) > args.maxlines:
            pages.append(cur)          # close current page at the sentence end
            cur = sent
        else:
            cur = cand
    if cur:
        pages.append(cur)
    if not pages:
        pages = [""]

    for idx, txt in enumerate(pages, start=1):
        page_text = "\n".join(wrapped(txt))
        (outdir / f"{args.prefix}{idx}.txt").write_text(page_text + "\n", encoding="utf-8")

    print(len(pages))


if __name__ == "__main__":
    main()
