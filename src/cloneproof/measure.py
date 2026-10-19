"""Turn two probes (reference, clone) plus a noise probe into numbers and a list of issues.

The idea that makes the score honest: a website never looks identical to itself twice
(carousels, video poster frames, timers, anti-aliasing). So we probe the reference twice,
mask every pixel that already differs between those two runs, and only count differences
outside that mask. A clone that is perfect scores ~100 even on a noisy site.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .probe import Probe

PIXEL_TOLERANCE = 14        # per-channel difference we treat as "the same pixel"
GRID = 32                   # cell size for locating difference regions
POS_TOL = 3.0               # px a box may move and still count as in place
SIZE_TOL = 3.0
MAX_ISSUES = 60

STYLE_KEYS = ("fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing", "color",
              "background", "borderRadius", "opacity", "textAlign", "textTransform", "backgroundImage", "boxShadow",
              "borderTopWidth", "borderTopColor")


@dataclass
class Issue:
    kind: str                # visual | missing | extra | text | position | size | style | font | asset | motion | height | console
    severity: float          # 0..1, how much a visitor would notice
    viewport: str
    summary: str
    selector: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "severity": round(self.severity, 3), "viewport": self.viewport,
                "summary": self.summary, "selector": self.selector, "detail": self.detail}


# -- pixels --------------------------------------------------------------------------------

def _arr(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.int16)


def _fit(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    return a[:h, :w], b[:h, :w]


def diff_mask(a: Image.Image, b: Image.Image, tol: int = PIXEL_TOLERANCE) -> np.ndarray:
    """Boolean array: True where the two frames differ by more than the tolerance."""
    x, y = _fit(_arr(a), _arr(b))
    return np.abs(x - y).max(axis=2) > tol


def noise_mask(a: Image.Image, b: Image.Image) -> np.ndarray:
    """Pixels that already differ between two runs of the SAME page, grown a little."""
    m = diff_mask(a, b, tol=6)
    if not m.any():
        return m
    img = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))
    return np.asarray(img) > 0


BAND = 48
MAX_SHIFT = 48


def align_bands(ref: Image.Image, clone: Image.Image) -> Image.Image:
    """Slide each horizontal band of the clone up/down to where it best matches the reference.

    A heading that is 10px taller pushes everything below it down by 10px. Without this, one
    small difference makes the whole rest of the page count as wrong. The shift itself is
    reported separately as a layout problem; here we only ask "does it LOOK the same".
    """
    ra = np.asarray(ref.convert("L"), dtype=np.int16)[:, ::2]
    ca = np.asarray(clone.convert("L"), dtype=np.int16)[:, ::2]
    h = ra.shape[0]
    cw = clone.convert("RGB")
    out = Image.new("RGB", ref.size, (255, 0, 255))
    cfull = np.asarray(cw)
    ofull = np.asarray(out).copy()
    w = min(ref.width, clone.width)
    for y0 in range(0, h, BAND):
        y1 = min(y0 + BAND, h)
        band = ra[y0:y1]
        best_dy, best = 0, None
        if band.std() > 1.5:
            def cost(dy: int) -> float:
                a, b = y0 + dy, y1 + dy
                if a < 0 or b > ca.shape[0]:
                    return 1e9
                return float(np.abs(band[:, : ca.shape[1]] - ca[a:b, : band.shape[1]]).mean()) + 0.02 * abs(dy)
            best = cost(0)
            for dy in range(-MAX_SHIFT, MAX_SHIFT + 1, 4):
                c = cost(dy)
                if c < best:
                    best, best_dy = c, dy
            for dy in range(best_dy - 3, best_dy + 4):
                c = cost(dy)
                if c < best:
                    best, best_dy = c, dy
        a, b = y0 + best_dy, y1 + best_dy
        if a >= 0 and b <= cfull.shape[0]:
            ofull[y0:y1, :w] = cfull[a:b, :w]
        else:
            lo, hi = max(a, 0), min(b, cfull.shape[0])
            if hi > lo:
                ofull[y0 + (lo - a): y0 + (lo - a) + (hi - lo), :w] = cfull[lo:hi, :w]
    return Image.fromarray(ofull)


def frame_similarity(ref: Image.Image, clone: Image.Image, mask: np.ndarray | None
                     ) -> tuple[float, float, np.ndarray]:
    """(raw match, content match, diff map) with noise removed.

    raw     = share of all pixels that match. Flat backgrounds inflate it.
    content = share of pixels that match among pixels where either image shows something other
              than the frame's dominant colour. This is the number the score uses.
    """
    raw_d = diff_mask(ref, clone)
    clone = align_bands(ref, clone) if raw_d.mean() > 0.002 else clone
    d = diff_mask(ref, clone)
    rh, rw = ref.height, ref.width
    full = np.ones((rh, rw), dtype=bool)          # outside the clone's canvas counts as different
    full[: d.shape[0], : d.shape[1]] = d
    valid = np.ones((rh, rw), dtype=bool)
    if mask is not None:
        mh, mw = min(mask.shape[0], rh), min(mask.shape[1], rw)
        valid[:mh, :mw] = ~mask[:mh, :mw]
    bad = full & valid
    raw_full = np.ones((rh, rw), dtype=bool)
    raw_full[: raw_d.shape[0], : raw_d.shape[1]] = raw_d
    raw = 1.0 - int((raw_full & valid).sum()) / (int(valid.sum()) or 1)

    ra = _arr(ref)
    q = (ra // 8).reshape(-1, 3)
    codes = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    mode = np.bincount(codes).argmax()
    ref_busy = (codes != mode).reshape(rh, rw)
    ca = np.zeros_like(ref_busy)
    cl = _arr(clone)
    cq = (cl // 8).reshape(-1, 3)
    ccodes = cq[:, 0] * 1024 + cq[:, 1] * 32 + cq[:, 2]
    cbusy = (ccodes != mode).reshape(cl.shape[0], cl.shape[1])
    ca[: cbusy.shape[0], : cbusy.shape[1]] = cbusy[:rh, :rw]
    outside = np.zeros((rh, rw), dtype=bool)          # what the clone does not have at all is always "busy"
    outside[min(cl.shape[0], rh):, :] = True
    outside[:, min(cl.shape[1], rw):] = True
    busy = (ref_busy | ca | outside) & valid
    n_busy = int(busy.sum())
    content = 1.0 - int((bad & busy).sum()) / n_busy if n_busy else 1.0
    return raw, content, bad


def regions_from_diff(diff: np.ndarray, min_cells: int = 2) -> list[tuple[int, int, int, int, float]]:
    """Group differing cells into boxes (x, y, w, h, density) with a simple flood fill."""
    h, w = diff.shape
    gh, gw = (h + GRID - 1) // GRID, (w + GRID - 1) // GRID
    pad = np.zeros((gh * GRID, gw * GRID), dtype=bool)
    pad[:h, :w] = diff
    cells = pad.reshape(gh, GRID, gw, GRID).mean(axis=(1, 3))
    hot = cells > 0.08
    seen = np.zeros_like(hot)
    boxes = []
    for gy in range(gh):
        for gx in range(gw):
            if not hot[gy, gx] or seen[gy, gx]:
                continue
            stack, members = [(gy, gx)], []
            seen[gy, gx] = True
            while stack:
                cy, cx = stack.pop()
                members.append((cy, cx))
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < gh and 0 <= nx < gw and hot[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(members) < min_cells:
                continue
            ys = [m[0] for m in members]
            xs = [m[1] for m in members]
            y0, y1, x0, x1 = min(ys) * GRID, (max(ys) + 1) * GRID, min(xs) * GRID, (max(xs) + 1) * GRID
            density = float(np.mean([cells[m] for m in members]))
            boxes.append((x0, y0, x1 - x0, y1 - y0, density))
    boxes.sort(key=lambda b: b[2] * b[3] * b[4], reverse=True)
    return boxes


def heatmap(ref: Image.Image, diff: np.ndarray) -> Image.Image:
    """The reference frame, dimmed, with every differing pixel painted red."""
    base = np.asarray(ref.convert("RGB"), dtype=np.float32) * 0.35 + 255 * 0.15
    h, w = base.shape[:2]
    d = np.zeros((h, w), dtype=bool)
    d[: min(h, diff.shape[0]), : min(w, diff.shape[1])] = diff[:h, :w]
    base[d] = (235, 40, 60)
    return Image.fromarray(base.astype(np.uint8))


def motion_profile(frames: list[Image.Image]) -> list[float]:
    """How much the picture changes between consecutive scroll positions (0..1)."""
    out = []
    for a, b in zip(frames, frames[1:]):
        out.append(float(diff_mask(a, b).mean()))
    return out


# -- DOM -----------------------------------------------------------------------------------

def _key(e: dict[str, Any]) -> str:
    if e["media"]:
        # file names change when a site is mirrored (hash suffixes, .webp -> .avif), so key on
        # what a visitor sees: the alt text, or else the rough size
        if e.get("alt"):
            return f"{e['tag']}|{e['alt'].lower()}"
        return f"{e['tag']}|~{round(e['w'] / 20) * 20}x{round(e['h'] / 20) * 20}"
    if e["text"]:
        return f"{e['tag']}|{e['text'][:60].lower()}"
    return f"{e['tag']}|box"


def match_elements(ref: list[dict], clone: list[dict]
                   ) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Align the two element lists. Returns (pairs, missing_in_clone, extra_in_clone)."""
    rk, ck = [_key(e) for e in ref], [_key(e) for e in clone]
    sm = difflib.SequenceMatcher(None, rk, ck, autojunk=False)
    pairs, used_r, used_c = [], set(), set()
    for blk in sm.get_matching_blocks():
        for i in range(blk.size):
            pairs.append((ref[blk.a + i], clone[blk.b + i]))
            used_r.add(blk.a + i)
            used_c.add(blk.b + i)
    # second chance: same key anywhere (the order changed)
    pool: dict[str, list[int]] = {}
    for j, k in enumerate(ck):
        if j not in used_c:
            pool.setdefault(k, []).append(j)
    for i, k in enumerate(rk):
        if i in used_r:
            continue
        if pool.get(k):
            j = pool[k].pop(0)
            pairs.append((ref[i], clone[j]))
            used_r.add(i)
            used_c.add(j)
    # third chance: same tag, nearly the same text (text was edited)
    for i, e in enumerate(ref):
        if i in used_r or not e["text"]:
            continue
        best, best_j = 0.0, -1
        for j, c in enumerate(clone):
            if j in used_c or c["tag"] != e["tag"] or not c["text"]:
                continue
            r = difflib.SequenceMatcher(None, e["text"].lower(), c["text"].lower()).quick_ratio()
            if r > best:
                best, best_j = r, j
        if best >= 0.75 and best_j >= 0:
            pairs.append((e, clone[best_j]))
            used_r.add(i)
            used_c.add(best_j)
    missing = [e for i, e in enumerate(ref) if i not in used_r]
    extra = [e for j, e in enumerate(clone) if j not in used_c]
    return pairs, missing, extra


def _num(v: str) -> float | None:
    m = re.match(r"^-?\d+(\.\d+)?", str(v))
    return float(m.group(0)) if m else None


def _color_dist(a: str, b: str) -> float:
    def parse(c: str) -> tuple[float, ...] | None:
        n = re.findall(r"[\d.]+", c)
        return tuple(float(x) for x in n[:4]) if len(n) >= 3 else None
    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return 0.0 if a == b else 255.0
    if len(pa) == 4 and pa[3] == 0 and len(pb) == 4 and pb[3] == 0:
        return 0.0
    return max(abs(x - y) for x, y in zip(pa[:3], pb[:3]))


def _style_diffs(r: dict, c: dict) -> dict[str, tuple[str, str]]:
    out = {}
    for k in STYLE_KEYS:
        a, b = r["s"].get(k, ""), c["s"].get(k, "")
        if a == b:
            continue
        if k in ("backgroundImage", "boxShadow"):
            if re.sub(r"https?://[^)\s]*/", "", a) == re.sub(r"https?://[^)\s]*/", "", b):
                continue
        elif k in ("borderTopWidth",):
            if a == b or (_num(a) is not None and _num(b) is not None and abs(_num(a) - _num(b)) < 0.6):
                continue
        elif k in ("color", "background", "borderTopColor"):
            if _color_dist(a, b) <= 6:
                continue
        elif k in ("fontSize", "lineHeight", "letterSpacing", "borderRadius"):
            na, nb = _num(a), _num(b)
            if na is not None and nb is not None and abs(na - nb) <= 0.6:
                continue
            if a == "normal" or b == "normal":
                if a == b:
                    continue
        elif k == "opacity":
            if abs(float(a or 1) - float(b or 1)) < 0.03:
                continue
        elif k == "fontFamily":
            if a.lower() == b.lower():
                continue
        if k in ("borderTopColor",) and (_num(r["s"].get("borderTopWidth", "0")) or 0) < 0.5:
            continue
        if r["text"] == "" and k in ("fontFamily", "fontSize", "fontWeight", "lineHeight",
                                    "letterSpacing", "textAlign", "textTransform", "color"):
            continue    # box without text: typography is invisible
        out[k] = (a, b)
    return out


def compare_elements(vp: str, ref: Probe, clone: Probe) -> tuple[dict[str, float], list[Issue]]:
    pairs, missing, extra = match_elements(ref.elements, clone.elements)
    issues: list[Issue] = []
    total_area = sum(e["w"] * e["h"] for e in ref.elements) or 1.0

    def weight(e: dict) -> float:
        return min(1.0, (e["w"] * e["h"]) / (ref.width * ref.height * 0.5) + (0.25 if e["text"] else 0.05))

    for e in missing:
        label = e["text"][:50] or e.get("src") or e["tag"]
        issues.append(Issue("missing", min(1.0, 0.35 + weight(e)), vp,
                            f'<{e["tag"]}> "{label}" is in the original but not in the clone',
                            e["path"], {"x": e["x"], "y": e["y"], "w": e["w"], "h": e["h"]}))
    for e in extra:
        label = e["text"][:50] or e.get("src") or e["tag"]
        issues.append(Issue("extra", min(1.0, 0.25 + weight(e)), vp,
                            f'<{e["tag"]}> "{label}" is in the clone but not in the original',
                            e["path"], {"x": e["x"], "y": e["y"], "w": e["w"], "h": e["h"]}))

    in_place = 0.0
    text_ok = 0
    style_w_bad = style_w_all = 0.0
    prev_dy = 0.0
    for r, c in sorted(pairs, key=lambda p: (p[0]["y"], p[0]["x"])):
        dx, dy = c["x"] - r["x"], c["y"] - r["y"]
        dw, dh = c["w"] - r["w"], c["h"] - r["h"]
        w = weight(r)
        # A shift inherited from an element above is a consequence, not a new mistake.
        introduced = abs(dy - prev_dy) > POS_TOL
        moved_x = abs(dx) > POS_TOL
        resized = max(abs(dw), abs(dh)) > SIZE_TOL and max(abs(dw) / max(r["w"], 1), abs(dh) / max(r["h"], 1)) > 0.01
        if not r["fixed"]:
            prev_dy = dy if (abs(dy) > POS_TOL or introduced) else 0.0
        if not introduced and not moved_x and not resized:
            in_place += 1.0 if abs(dy) <= POS_TOL else 0.85
        if introduced or moved_x:
            ex, ey = (dx if moved_x else 0.0), (dy - (prev_dy if not introduced else 0.0) if introduced else 0.0)
            issues.append(Issue("position", min(1.0, 0.15 + w * min(1.0, max(abs(ex), abs(dy)) / 80)), vp,
                                f'`{r["path"]}` is {fmt_delta(dx if moved_x else 0, dy if introduced else 0)} off the original position',
                                r["path"], {"dx": round(dx, 1), "dy": round(dy, 1),
                                            "ref_x": r["x"], "ref_y": r["y"]}))
        if resized:
            issues.append(Issue("size", min(1.0, 0.15 + w * min(1.0, max(abs(dw), abs(dh)) / 80)), vp,
                                f'`{r["path"]}` is {c["w"]:.0f}x{c["h"]:.0f}px, original is {r["w"]:.0f}x{r["h"]:.0f}px',
                                r["path"], {"ref_w": r["w"], "ref_h": r["h"], "w": c["w"], "h": c["h"]}))
        sd = _style_diffs(r, c)
        style_w_all += max(w, 0.05)
        if sd:
            style_w_bad += max(w, 0.05) * min(1.0, 0.4 + 0.2 * len(sd))
        for k, (a_, b_) in sd.items():
            sev = 0.12 + w * (0.9 if k in ("fontSize", "fontFamily", "color", "background") else 0.5)
            issues.append(Issue("style", min(1.0, sev), vp,
                                f'`{r["path"]}` {css_name(k)}: original {a_}, clone {b_}',
                                r["path"], {"property": css_name(k), "original": a_, "clone": b_}))
        if r["text"]:
            if r["text"] == c["text"]:
                text_ok += 1
            else:
                issues.append(Issue("text", min(1.0, 0.3 + w), vp,
                                    f'text differs in `{r["path"]}`: original "{r["text"][:70]}", clone "{c["text"][:70]}"',
                                    r["path"], {"original": r["text"], "clone": c["text"]}))

    n_ref = max(len(ref.elements), 1)
    area_w = lambda e: (e["w"] * e["h"]) / total_area  # noqa: E731
    matched_area = sum(area_w(r) for r, _ in pairs)
    if not ref.elements and not clone.elements:
        layout = 1.0
    else:
        layout = (in_place / n_ref) * 0.6 + matched_area * 0.4
    typography = 1.0 - (style_w_bad / style_w_all) if style_w_all else (1.0 if not ref.elements else 0.0)
    texty = [e for e in ref.elements if e["text"]]
    content = (text_ok / len(texty)) if texty else 1.0
    return {"layout": min(layout, 1.0), "style": max(typography, 0.0), "content": min(content, 1.0)}, issues


def fmt_delta(dx: float, dy: float) -> str:
    parts = []
    if abs(dx) > POS_TOL:
        parts.append(f"{abs(dx):.0f}px too far {'right' if dx > 0 else 'left'}")
    if abs(dy) > POS_TOL:
        parts.append(f"{abs(dy):.0f}px too {'low' if dy > 0 else 'high'}")
    return " and ".join(parts) or "slightly"


def css_name(k: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), k)


# -- assets / behaviour ----------------------------------------------------------------------

def compare_assets(vp: str, ref: Probe, clone: Probe) -> tuple[float, list[Issue]]:
    issues: list[Issue] = []
    gone: list[str] = []
    fonts_ref, fonts_clone = set(ref.fonts), set(clone.fonts)
    for f in sorted(x for x in fonts_ref - fonts_clone if "fallback" not in x.lower())[:6]:
        issues.append(Issue("font", 0.55, vp, f"font not loaded in clone: {f}", "", {"font": f}))
    for u in clone.failed_requests[:8]:
        issues.append(Issue("asset", 0.4, vp, f"clone request failed: {u}", "", {}))
    for g in gone[:8]:
        issues.append(Issue("asset", 0.2, vp, f"asset used by the original is never requested by the clone: {g}", "", {}))
    for m in sorted(set(clone.console_errors) - set(ref.console_errors))[:5]:
        issues.append(Issue("console", 0.3, vp, f"console error only in the clone: {m.splitlines()[0][:120]}", "", {}))
    score = 1.0
    score -= min(0.4, 0.1 * len([x for x in fonts_ref - fonts_clone if "fallback" not in x.lower()]))
    score -= min(0.4, 0.08 * len(clone.failed_requests))
    return max(score, 0.0), issues


def compare_motion(vp: str, ref_frames: list[Image.Image], clone_frames: list[Image.Image]
                   ) -> tuple[float, list[Issue]]:
    rp, cp = motion_profile(ref_frames), motion_profile(clone_frames)
    n = min(len(rp), len(cp))
    if n == 0:
        return 1.0, []
    a, b = np.array(rp[:n]), np.array(cp[:n])
    denom = float(np.maximum(a, b).sum())
    if denom < 1e-6:
        return 1.0, []
    score = 1.0 - float(np.abs(a - b).sum()) / denom
    issues: list[Issue] = []
    for i in range(n):
        hi, lo = max(a[i], b[i]), min(a[i], b[i])
        if hi > 0.12 and lo < hi * 0.4:
            who = "the clone is more static than the original" if b[i] < a[i] else "the clone moves where the original does not"
            issues.append(Issue("motion", 0.35, vp, f"scroll step {i + 1}->{i + 2}: {who} "
                                f"(change {a[i]*100:.0f}% vs {b[i]*100:.0f}% of pixels)", "",
                                {"step": i + 1, "original": round(float(a[i]), 3), "clone": round(float(b[i]), 3)}))
    return max(score, 0.0), issues
