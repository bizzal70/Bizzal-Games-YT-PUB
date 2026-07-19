#!/usr/bin/env python3
"""
build_thumbnail.py -- compose a 1280x720 YouTube thumbnail from a background
image + the ruling title, so long-form videos stop auto-serving a random frame.

The title is drawn big, bold, high-contrast (white with a heavy black stroke)
over a darkened cover-cropped background, with a bottom gradient for legibility.

Usage:
    build_thumbnail.py --bg BG.png --title "The ruling" --out DAY.thumb.jpg
        [--icon assets/brand/channel_icon.png]

Fail-soft by contract: callers treat a non-zero exit as "no custom thumbnail"
and continue. Requires Pillow.
"""
import argparse
import sys

W, H = 1280, 720
MARGIN = 64
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _cover_crop(img, w, h):
    """Scale to cover w x h, center-crop the overflow."""
    from PIL import Image
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    img = img.resize(new, Image.LANCZOS)
    left = (img.size[0] - w) // 2
    top = (img.size[1] - h) // 2
    return img.crop((left, top, left + w, top + h))


def _wrap_to_width(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_text(draw, text, max_w, max_h, max_lines=3):
    """Pick the largest font size where the wrapped title fits the text box."""
    for size in range(120, 47, -4):
        font = _load_font(size)
        lines = _wrap_to_width(draw, text, font, max_w)
        if len(lines) > max_lines:
            continue
        line_h = (font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) + 14
        if line_h * len(lines) <= max_h:
            return font, lines, line_h
    font = _load_font(52)
    return font, _wrap_to_width(draw, text, font, max_w)[:max_lines], 66


def build(bg_path, title, out_path, icon_path=None):
    from PIL import Image, ImageDraw

    bg = Image.open(bg_path).convert("RGB")
    canvas = _cover_crop(bg, W, H)

    # Darken overall + a stronger bottom gradient where the text sits.
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 90))
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), int(200 * (y / H) ** 1.6))
    grad = grad.resize((W, H))
    black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    black.putalpha(grad)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    canvas = Image.alpha_composite(canvas, black).convert("RGB")

    draw = ImageDraw.Draw(canvas)
    text = " ".join((title or "").split()).upper()
    box_w = W - 2 * MARGIN
    box_h = int(H * 0.62)
    font, lines, line_h = _fit_text(draw, text, box_w, box_h)

    total_h = line_h * len(lines)
    y = H - MARGIN - total_h
    for line in lines:
        draw.text(
            (MARGIN, y), line, font=font, fill=(255, 255, 255),
            stroke_width=max(4, font.size // 14), stroke_fill=(0, 0, 0),
        )
        y += line_h

    if icon_path:
        try:
            icon = Image.open(icon_path).convert("RGBA")
            side = 120
            icon = icon.resize((side, side), Image.LANCZOS)
            canvas.paste(icon, (W - side - 32, 32), icon)
        except Exception:
            pass

    # JPEG, quality tuned to stay well under YouTube's 2MB limit.
    q = 90
    canvas.save(out_path, "JPEG", quality=q)
    import os
    while os.path.getsize(out_path) > 2_000_000 and q > 50:
        q -= 8
        canvas.save(out_path, "JPEG", quality=q)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bg", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--icon", default="")
    args = ap.parse_args()
    try:
        out = build(args.bg, args.title, args.out, args.icon or None)
        print(f"[build_thumbnail] wrote {out}")
    except Exception as exc:  # fail-soft: never block the pipeline
        print(f"[build_thumbnail] WARN: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
