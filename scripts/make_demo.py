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
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (11, 13, 18))
    d = ImageDraw.Draw(img)
    d.text((60, 40), "cloneproof", font=font(54), fill=(255, 255, 255))
    d.text((60, 112), f"round {rnd} of {total}", font=font(30), fill=(140, 148, 165))
    if rnd == 1:
        line = "The AI says it is done. cloneproof says:"
    elif rnd == total:
        line = f"{rnd - 1} rounds of measure, fix, measure."
    else:
        line = "cloneproof lists the differences. The agent fixes them."
    d.text((60, 175), line, font=font(34), fill=(232, 235, 242))
    base = rdir / vp
    for i, (name, label) in enumerate((("original", "original"), ("clone", "AI clone"), ("diff", "difference"))):
        p = base / f"{frame:02d}-{name}.png"
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((590, 400))
        x = 60 + i * 620
        d.text((x, 245), label, font=font(28), fill=(140, 148, 165))
        img.paste(im, (x, 290))
    d.text((60, 740), f"{score:.1f}", font=font(230), fill=colour(score))
    d.text((590, 880), "/ 100", font=font(48), fill=(140, 148, 165))
    vps = " + ".join(rep["viewports"].keys())
    d.text((60, 1000), f"score over: {vps}", font=font(24), fill=(140, 148, 165))
    x0, y0, w, h = 800, 740, 1060, 260
    d.rectangle((x0, y0, x0 + w, y0 + h), outline=(37, 43, 59))
    for g in (50, 75, 100):
        gy = y0 + h - int(h * g / 100)
        d.line((x0, gy, x0 + w, gy), fill=(30, 35, 48))
        d.text((x0 + w + 8, gy - 12), str(g), font=font(20), fill=(100, 108, 125))
    pts = history[: rnd]
    for k in range(len(pts)):
        px = x0 + 20 + int((w - 40) * (k / max(total - 1, 1)))
        py = y0 + h - int(h * pts[k] / 100)
        if k:
            qx = x0 + 20 + int((w - 40) * ((k - 1) / max(total - 1, 1)))
            qy = y0 + h - int(h * pts[k - 1] / 100)
            d.line((qx, qy, px, py), fill=(99, 102, 241), width=5)
        d.ellipse((px - 9, py - 9, px + 9, py + 9), fill=colour(pts[k]))
    d.text((60, 1030), "github.com/pcjansen09-max/cloneproof", font=font(24), fill=(100, 108, 125))
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
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "0.7", "-i", str(out / "card-%02d.png"),
                    "-vf", "format=yuv420p", "-movflags", "+faststart", str(out / "demo.mp4")], check=False)
    print(out, history)


if __name__ == "__main__":
    main()
