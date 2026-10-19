"""Social video (about 25 s, 1920x1080) from a real loop run.

usage: python scripts/make_social.py out/demo-run out/social [frame-index] [viewport]
Scenes: the AI says done / cloneproof says 57 / the differences it found / the rounds / the result.
Every number and sentence on the cards comes from the run's report.json files.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from make_demo import card, colour, font  # noqa: E402

W, H = 1920, 1080
BG = (11, 13, 18)


def blank():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def centered(d, text, y, size, fill=(255, 255, 255)):
    f = font(size)
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


def wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def scene_title():
    img, d = blank()
    centered(d, "You asked an AI to clone a website.", 340, 70)
    centered(d, "It said:  “Done. Pixel-perfect.”", 460, 80, (234, 179, 8))
    return img


def scene_score(first: Path, frame: int, vp: str):
    img, d = blank()
    rep = json.loads((first / "report.json").read_text())
    centered(d, "cloneproof measured it:", 90, 60)
    base = first / vp
    for i, name in enumerate(("original", "clone")):
        im = Image.open(base / f"{frame:02d}-{name}.png").convert("RGB")
        im.thumbnail((800, 520))
        x = 120 + i * 880
        d.text((x, 200), "original" if i == 0 else "the AI's clone", font=font(30), fill=(140, 148, 165))
        img.paste(im, (x, 250))
    s = rep["score"]
    centered(d, f"{s:.1f} / 100", 790, 150, colour(s))
    centered(d, "score over: " + " + ".join(rep["viewports"].keys()), 975, 28, (140, 148, 165))
    return img


def scene_issues(first: Path, frame: int, vp: str):
    img, d = blank()
    rep = json.loads((first / "report.json").read_text())
    centered(d, "Here is exactly what is different", 70, 60)
    im = Image.open(first / vp / f"{frame:02d}-diff.png").convert("RGB")
    im.thumbnail((820, 700))
    img.paste(im, (80, 230))
    seen, y = set(), 240
    f = font(30)
    for i in rep["issues"]:
        if i["viewport"] != vp or i["kind"] not in ("style", "size", "position", "text", "font") or i["summary"] in seen \
                or abs(i.get("detail", {}).get("dy", 0)) > 400:
            continue
        seen.add(i["summary"])
        text = i["summary"].replace("`", "")
        for line in wrap(d, text, f, 880)[:2]:
            d.text((960, y), line, font=f, fill=(232, 235, 242))
            y += 40
        y += 22
        if y > 900 or len(seen) >= 8:
            break
    return img


def scene_result(scores):
    img, d = blank()
    centered(d, "One agent, one loop, measure, fix, measure", 80, 56)
    s = scores[-1]
    centered(d, f"{scores[0]:.0f}  →  {s:.1f}", 260, 230, colour(s))
    centered(d, f"in {len(scores)} rounds", 560, 60, (140, 148, 165))
    x0, y0, w, h = 360, 700, 1200, 220
    d.rectangle((x0, y0, x0 + w, y0 + h), outline=(37, 43, 59))
    for k, v in enumerate(scores):
        px = x0 + 20 + int((w - 40) * k / max(len(scores) - 1, 1))
        py = y0 + h - int(h * v / 100)
        if k:
            qx = x0 + 20 + int((w - 40) * (k - 1) / max(len(scores) - 1, 1))
            qy = y0 + h - int(h * scores[k - 1] / 100)
            d.line((qx, qy, px, py), fill=(99, 102, 241), width=6)
        d.ellipse((px - 10, py - 10, px + 10, py + 10), fill=colour(v))
    return img


def scene_end():
    img, d = blank()
    centered(d, "cloneproof", 330, 130)
    centered(d, "Don't ask your AI to clone a website. Make it prove it.", 500, 46, (232, 235, 242))
    centered(d, "github.com/pcjansen09-max/cloneproof", 640, 54, (99, 102, 241))
    centered(d, "free, local, MIT", 740, 36, (140, 148, 165))
    return img


def main():
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    frame = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    vp = sys.argv[4] if len(sys.argv) > 4 else "desktop"
    out.mkdir(parents=True, exist_ok=True)
    rounds = sorted(p for p in run.glob("round-*") if (p / "report.json").exists())
    scores = [json.loads((r / "report.json").read_text())["score"] for r in rounds]
    plan = [(scene_title(), 2.8), (scene_score(rounds[0], frame, vp), 3.5), (scene_issues(rounds[0], frame, vp), 5.0)]
    for i, r in enumerate(rounds[1:], 2):
        plan.append((card(r, frame, vp, i, len(rounds), scores), 1.1))
    plan += [(scene_result(scores), 4.0), (scene_end(), 3.5)]
    lines = []
    for i, (img, secs) in enumerate(plan):
        p = out / f"s{i:02d}.png"
        img.save(p)
        lines += [f"file '{p.resolve()}'", f"duration {secs}"]
    lines.append(f"file '{(out / f's{len(plan) - 1:02d}.png').resolve()}'")
    (out / "list.txt").write_text("\n".join(lines))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(out / "list.txt"),
                    "-vf", "fps=30,format=yuv420p", "-movflags", "+faststart", str(out / "cloneproof-demo.mp4")], check=True)
    total = sum(s for _, s in plan)
    print(out / "cloneproof-demo.mp4", f"{total:.0f}s", scores)


if __name__ == "__main__":
    main()
