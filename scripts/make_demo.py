"""Turn a `cloneproof loop` run into a shareable demo: GIF + MP4 + a score-curve strip.

usage: python scripts/make_demo.py .cloneproof out/demo [frame-index] [viewport]
Each round becomes a card: original | clone | difference, big score, round number.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size):
    for p in FONTS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def colour(score):
    return (34, 197, 94) if score >= 97 else (132, 204, 22) if score >= 90 else (234, 179, 8) if score >= 80 else (249, 115, 22) if score >= 60 else (239, 68, 68)


def card(rdir: Path, frame: int, vp: str, rnd: int, total: int, history: list[float]) -> Image.Image:
    rep = json.loads((rdir / "report.json").read_text())
    score = rep["score"]
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (11, 13, 18))
    d = ImageDraw.Draw(img)
    d.text((40, 28), "cloneproof loop", font=font(30), fill=(255, 255, 255))
    d.text((40, 70), f"round {rnd} of {total}", font=font(20), fill=(140, 148, 165))
    base = rdir / vp
    for i, (name, label) in enumerate((("original", "original"), ("clone", "AI clone"), ("diff", "difference"))):
        p = base / f"{frame:02d}-{name}.png"
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((390, 390))
        x = 40 + i * 410
        d.text((x, 112), label, font=font(18), fill=(140, 148, 165))
        img.paste(im, (x, 140))
    d.text((40, 570), f"{score:.1f}", font=font(110), fill=colour(score))
    d.text((330, 610), "/ 100", font=font(30), fill=(140, 148, 165))
    # score curve
    x0, y0, w, h = 560, 560, 680, 120
    d.rectangle((x0, y0, x0 + w, y0 + h), outline=(37, 43, 59))
    pts = history[: rnd]
    for k in range(len(pts)):
        px = x0 + int(w * (k / max(total - 1, 1)))
        py = y0 + h - int(h * pts[k] / 100)
        d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=colour(pts[k]))
        if k:
            qx = x0 + int(w * ((k - 1) / max(total - 1, 1)))
            qy = y0 + h - int(h * pts[k - 1] / 100)
            d.line((qx, qy, px, py), fill=(99, 102, 241), width=3)
    return img


def main():
    run = Path(sys.argv[1])
    out = Path(sys.argv[2])
    frame = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    vp = sys.argv[4] if len(sys.argv) > 4 else "desktop"
    out.mkdir(parents=True, exist_ok=True)
    rounds = sorted(p for p in run.glob("round-*") if (p / "report.json").exists())
    history = [json.loads((r / "report.json").read_text())["score"] for r in rounds]
    cards = [card(r, frame, vp, i + 1, len(rounds), history) for i, r in enumerate(rounds)]
    for i, c in enumerate(cards):
        c.save(out / f"card-{i + 1:02d}.png")
    seq = cards + [cards[-1]] * 2
    seq[0].save(out / "demo.gif", save_all=True, append_images=seq[1:], duration=1600, loop=0, optimize=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "0.6", "-i", str(out / "card-%02d.png"),
                    "-vf", "format=yuv420p", "-movflags", "+faststart", str(out / "demo.mp4")], check=False)
    print(out, history)


if __name__ == "__main__":
    main()
