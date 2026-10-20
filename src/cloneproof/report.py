"""Human-facing output: report.html, report.md and a shareable score card image."""

from __future__ import annotations

import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .compare import Result, verdict
from .prompt import dedupe

FONT_CANDIDATES = [
    "/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for p in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _colour(score: float) -> tuple[int, int, int]:
    if score >= 97:
        return (34, 197, 94)
    if score >= 90:
        return (132, 204, 22)
    if score >= 80:
        return (234, 179, 8)
    if score >= 60:
        return (249, 115, 22)
    return (239, 68, 68)


def scorecard(result: Result, path: Path) -> None:
    """1200x630 image, made to be posted: both sites, the score, the per-device numbers."""
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (11, 13, 18))
    d = ImageDraw.Draw(img)
    vp = result.viewports.get("desktop") or next(iter(result.viewports.values()))
    d.text((48, 36), "cloneproof", font=_font(34), fill=(255, 255, 255))
    d.text((48, 82), "how close is the clone, really?", font=_font(20), fill=(140, 148, 165))

    def paste(src: Path, x: int, label: str) -> None:
        if not src.exists():
            return
        im = Image.open(src).convert("RGB")
        im.thumbnail((330, 360))
        box = Image.new("RGB", (im.width + 8, im.height + 8), (40, 46, 60))
        box.paste(im, (4, 4))
        img.paste(box, (x, 150))
        d.text((x, 124), label, font=_font(18), fill=(140, 148, 165))

    # pick the frame with the most going on in the middle of the page
    idx = min(len(vp.frames) // 2, len(vp.frames) - 1) if vp.frames else 0
    base = result.out_dir / vp.name
    paste(base / f"{idx:02d}-original.png", 48, "original")
    paste(base / f"{idx:02d}-clone.png", 410, "clone")
    paste(base / f"{idx:02d}-diff.png", 772, "difference")

    score = result.score
    col = _colour(score)
    d.text((48, 450), f"{score:.1f}", font=_font(120), fill=col)
    d.text((330, 478), "/ 100", font=_font(36), fill=(140, 148, 165))
    d.text((330, 524), verdict(score), font=_font(30), fill=(255, 255, 255))
    x = 700
    for n, v in result.viewports.items():
        d.text((x, 478), n, font=_font(20), fill=(140, 148, 165))
        d.text((x, 508), f"{v.score:.0f}", font=_font(44), fill=_colour(v.score))
        x += 160
    d.text((48, 596), "github.com/pcjansen09-max/cloneproof", font=_font(18), fill=(100, 108, 125))
    img.save(path)


def markdown(result: Result) -> str:
    d = result.to_dict()
    out = [f"# cloneproof report", "",
           f"- original: {result.reference}", f"- clone: {result.clone}",
           f"- **score {d['score']} / 100: {d['verdict']}**", ""]
    out += ["| viewport | score | visual | layout | style | content | assets | motion |", "|---|---|---|---|---|---|---|---|"]
    for n, v in d["viewports"].items():
        c = v["categories"]
        out.append(f"| {n} | {v['score']} | {c['visual']} | {c['layout']} | {c['style']} | {c['content']} | "
                   f"{c['assets']} | {c['motion']} |")
    out += ["", "## Top differences", ""]
    for i, iss in enumerate(dedupe(result.issues())[:30], 1):
        out.append(f"{i}. [{iss.viewport}] {iss.summary}")
    return "\n".join(out) + "\n"


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>cloneproof report</title>
<style>
:root{--bg:#0b0d12;--card:#141824;--fg:#e8ebf2;--mut:#8c94a5;--line:#252b3b;--ok:#22c55e;--warn:#eab308;--bad:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 16px 80px}
h1{font-size:28px;margin:0 0 4px}.mut{color:var(--mut)}
.hero{display:flex;gap:28px;align-items:center;flex-wrap:wrap;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;margin:18px 0}
.big{font-size:84px;font-weight:800;line-height:1;letter-spacing:-2px}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;border:1px solid var(--line);font-size:13px;color:var(--mut)}
.vps{display:flex;gap:12px;flex-wrap:wrap}.vp{background:#0f1320;border:1px solid var(--line);border-radius:12px;padding:10px 16px;min-width:120px}
.vp b{font-size:26px;display:block}
.cats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.cat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.bar{height:6px;background:#202637;border-radius:3px;margin-top:6px;overflow:hidden}.bar i{display:block;height:100%}
.tabs{display:flex;gap:8px;margin:26px 0 10px}.tabs button{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 14px;cursor:pointer;font-size:14px}
.tabs button.on{border-color:#6366f1;background:#1b2040}
.frame{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:12px 0}
.frame h3{margin:0 0 8px;font-size:14px;color:var(--mut);font-weight:600}
.cmp{position:relative;max-width:100%;overflow:hidden;border-radius:8px;border:1px solid var(--line);background:#000;user-select:none}
.cmp img{display:block;width:100%;height:auto}.cmp .top{position:absolute;inset:0;overflow:hidden;width:50%}
.cmp .top img{width:var(--w);max-width:none}.cmp .handle{position:absolute;top:0;bottom:0;width:3px;background:#6366f1;left:50%}
.modes{display:flex;gap:6px;margin-bottom:8px}.modes button{background:#0f1320;color:var(--mut);border:1px solid var(--line);border-radius:6px;padding:3px 10px;cursor:pointer;font-size:12px}.modes button.on{color:#fff;border-color:#6366f1}
ol.issues{padding-left:22px}ol.issues li{margin:6px 0}code{background:#0f1320;padding:1px 6px;border-radius:5px;font-size:13px}
.sev{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
pre{background:#0f1320;border:1px solid var(--line);border-radius:10px;padding:14px;overflow:auto;white-space:pre-wrap;font-size:13px}
</style><body><div class="wrap">
<h1>cloneproof</h1><div class="mut">__REF__ &rarr; __CLONE__</div>
<div class="hero"><div><div class="big" style="color:__COL__">__SCORE__</div><div class="mut">out of 100 &middot; __VERDICT__</div></div>
<div class="vps">__VPS__</div></div>
<div class="cats">__CATS__</div>
<h2>Biggest differences</h2><ol class="issues">__ISSUES__</ol>
<h2>Frames</h2><div class="tabs">__TABS__</div>__FRAMES__
<h2>Prompt for your AI agent</h2><p class="mut">Paste this into Claude Code, Codex, Cursor, or let <code>cloneproof loop</code> do it.</p><pre>__PROMPT__</pre>
</div>
<script>
const tabs=document.querySelectorAll('.tabs button');
function show(n){tabs.forEach(b=>b.classList.toggle('on',b.dataset.vp===n));document.querySelectorAll('.vpframes').forEach(x=>x.style.display=x.dataset.vp===n?'block':'none')}
tabs.forEach(b=>b.onclick=()=>show(b.dataset.vp));show(tabs[0].dataset.vp);
document.querySelectorAll('.cmp').forEach(c=>{
  const top=c.querySelector('.top'),h=c.querySelector('.handle'),im=top.querySelector('img');
  const fit=()=>im.style.setProperty('--w',c.clientWidth+'px');fit();addEventListener('resize',fit);
  const mv=e=>{const r=c.getBoundingClientRect();const x=Math.min(Math.max((e.touches?e.touches[0].clientX:e.clientX)-r.left,0),r.width);top.style.width=x+'px';h.style.left=x+'px'};
  c.addEventListener('mousemove',mv);c.addEventListener('touchmove',mv);
});
document.querySelectorAll('.modes').forEach(m=>{
  m.querySelectorAll('button').forEach(b=>b.onclick=()=>{
    const f=m.parentElement;m.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
    f.querySelector('.slider').style.display=b.dataset.m==='slider'?'block':'none';
    f.querySelector('.diffimg').style.display=b.dataset.m==='diff'?'block':'none';
  });
});
</script></body></html>"""


def _bar(label: str, value: float) -> str:
    c = "#22c55e" if value >= 90 else "#eab308" if value >= 70 else "#ef4444"
    return (f'<div class="cat"><span class="mut">{label}</span> <b style="float:right">{value:.0f}</b>'
            f'<div class="bar"><i style="width:{value:.0f}%;background:{c}"></i></div></div>')


def write_html(result: Result, prompt_text: str, path: Path) -> None:
    d = result.to_dict()
    col = "#%02x%02x%02x" % _colour(result.score)
    vps = "".join(f'<div class="vp"><span class="mut">{n}</span><b style="color:#%02x%02x%02x">{v["score"]}</b></div>' % _colour(v["score"])
                  for n, v in d["viewports"].items())
    cats = {}
    for v in d["viewports"].values():
        for k, x in v["categories"].items():
            cats.setdefault(k, []).append(x)
    cat_html = "".join(_bar(k, sum(v) / len(v)) for k, v in cats.items())
    issues = "".join(
        f'<li><span class="sev" style="background:{"#ef4444" if i.severity > .6 else "#eab308" if i.severity > .35 else "#8c94a5"}"></span>'
        f'<span class="pill">{i.viewport}</span> {html.escape(i.summary).replace("`", "")}</li>'
        for i in dedupe(result.issues())[:30])
    tabs = "".join(f'<button data-vp="{n}">{n}</button>' for n in d["viewports"])
    frames = []
    for n, v in d["viewports"].items():
        block = [f'<div class="vpframes" data-vp="{n}">']
        for f in v["frames"]:
            i = f["index"]
            base = f"{n}/{i:02d}"
            block.append(
                f'<div class="frame"><h3>scroll {f["scroll_y"]}px &middot; {f["match"]}% match</h3>'
                f'<div class="modes"><button class="on" data-m="slider">slider</button><button data-m="diff">difference</button></div>'
                f'<div class="cmp slider"><img src="{base}-clone.png" loading="lazy"><div class="top"><img src="{base}-original.png" loading="lazy"></div><div class="handle"></div></div>'
                f'<div class="cmp diffimg" style="display:none"><img src="{base}-diff.png" loading="lazy"></div></div>')
        block.append("</div>")
        frames.append("".join(block))
    page = (PAGE.replace("__REF__", html.escape(result.reference)).replace("__CLONE__", html.escape(result.clone))
            .replace("__SCORE__", f"{result.score:.1f}").replace("__VERDICT__", verdict(result.score))
            .replace("__COL__", col).replace("__VPS__", vps).replace("__CATS__", cat_html)
            .replace("__ISSUES__", issues).replace("__TABS__", tabs).replace("__FRAMES__", "".join(frames))
            .replace("__PROMPT__", html.escape(prompt_text)))
    path.write_text(page, encoding="utf-8")


def write_all(result: Result, prompt_text: str) -> None:
    out = result.out_dir
    (out / "report.json").write_text(json.dumps(result.to_dict(max_issues=400), indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(markdown(result), encoding="utf-8")
    (out / "prompt.md").write_text(prompt_text, encoding="utf-8")
    write_html(result, prompt_text, out / "report.html")
    scorecard(result, out / "scorecard.png")


def badge_svg(score: float, label: str = "cloneproof") -> str:
    """A flat shields-style badge: `cloneproof | 97.1 / 100`. Colour follows the verdict."""
    msg = f"{score:.1f} / 100"
    col = "#%02x%02x%02x" % _colour(score)
    lw = 7 * len(label) + 20            # rough text widths, good enough for a badge
    mw = 7 * len(msg) + 20
    w = lw + mw
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" '
            f'aria-label="{html.escape(label)}: {html.escape(msg)}">'
            f'<title>{html.escape(label)}: {html.escape(msg)}</title>'
            f'<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
            f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
            f'<clipPath id="r"><rect width="{w}" height="20" rx="3" fill="#fff"/></clipPath>'
            f'<g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#555"/>'
            f'<rect x="{lw}" width="{mw}" height="20" fill="{col}"/><rect width="{w}" height="20" fill="url(#s)"/></g>'
            f'<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
            f'<text x="{lw / 2:.0f}" y="14">{html.escape(label)}</text>'
            f'<text x="{lw + mw / 2:.0f}" y="14">{html.escape(msg)}</text></g></svg>')
