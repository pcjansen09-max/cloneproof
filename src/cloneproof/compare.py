"""Compare a reference site to a clone: probe, measure, score, write artifacts."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from . import measure as M
from .browser import LAUNCH_ARGS
from .probe import VIEWPORTS, Probe, probe_page

WEIGHTS = {"visual": 0.50, "layout": 0.20, "style": 0.12, "content": 0.08, "assets": 0.05, "motion": 0.05}
VIEWPORT_WEIGHTS = {"desktop": 0.45, "mobile": 0.35, "tablet": 0.20}


@dataclass
class ViewportResult:
    name: str
    scores: dict[str, float]
    pixel_match_raw: float
    ref_height: int
    clone_height: int
    noise_pct: float
    frames: list[dict[str, Any]] = field(default_factory=list)
    issues: list[M.Issue] = field(default_factory=list)
    structure: list[dict[str, Any]] = field(default_factory=list)

    @property
    def score(self) -> float:
        return sum(self.scores[k] * w for k, w in WEIGHTS.items()) * 100


@dataclass
class Result:
    reference: str
    clone: str
    viewports: dict[str, ViewportResult]
    seconds: float
    out_dir: Path

    @property
    def score(self) -> float:
        total = sum(VIEWPORT_WEIGHTS[v] for v in self.viewports)
        return sum(r.score * VIEWPORT_WEIGHTS[v] for v, r in self.viewports.items()) / total

    def issues(self) -> list[M.Issue]:
        allv = [i for v in self.viewports.values() for i in v.issues]
        return sorted(allv, key=lambda i: i.severity, reverse=True)

    def to_dict(self, max_issues: int = M.MAX_ISSUES) -> dict[str, Any]:
        return {
            "reference": self.reference, "clone": self.clone,
            "score": round(self.score, 1),
            "verdict": verdict(self.score),
            "viewports": {
                n: {"score": round(v.score, 1),
                    "categories": {k: round(x * 100, 1) for k, x in v.scores.items()},
                    "pixel_match_raw": round(v.pixel_match_raw * 100, 1),
                    "noise_masked_pct": round(v.noise_pct, 2),
                    "page_height": {"reference": v.ref_height, "clone": v.clone_height},
                    "frames": v.frames, "structure": v.structure}
                for n, v in self.viewports.items()},
            "issues": [i.to_dict() for i in self.issues()[:max_issues]],
            "issue_count": len(self.issues()),
            "seconds": round(self.seconds, 1),
            "artifacts": str(self.out_dir),
        }


def verdict(score: float) -> str:
    if score >= 97:
        return "indistinguishable"
    if score >= 92:
        return "very close"
    if score >= 80:
        return "close, visible differences"
    if score >= 60:
        return "recognisable, clearly different"
    return "far off"


async def _one_viewport(browser, vp: str, ref_url: str, clone_url: str, out: Path, *,
                        wait_ms: int, settle_ms: int, noise: bool, max_frames: int,
                        say: Callable[[str], None], headers: dict | None) -> ViewportResult:
    say(f"[{vp}] loading reference")
    ref = await probe_page(browser, ref_url, vp, wait_ms=wait_ms, settle_ms=settle_ms,
                           max_frames=max_frames, headers=headers)
    say(f"[{vp}] loading clone")
    clone = await probe_page(browser, clone_url, vp, wait_ms=wait_ms, settle_ms=settle_ms,
                             positions=ref.positions, headers=headers)
    ref2 = None
    if noise:
        say(f"[{vp}] measuring the reference's own noise")
        ref2 = await probe_page(browser, ref_url, vp, wait_ms=wait_ms, settle_ms=settle_ms,
                                positions=ref.positions, headers=headers)

    vdir = out / vp
    vdir.mkdir(parents=True, exist_ok=True)
    raws, contents, frames_info = [], [], []
    noise_cells = []
    for i, y in enumerate(ref.positions):
        mask = M.noise_mask(ref.frames[i], ref2.frames[i]) if ref2 else None
        if mask is not None:
            noise_cells.append(float(mask.mean()))
        clone_frame = clone.frames[i] if i < len(clone.frames) else Image.new("RGB", ref.frames[i].size, (255, 0, 255))
        raw, content, diff = M.frame_similarity(ref.frames[i], clone_frame, mask)
        raws.append(raw)
        contents.append(content)
        regions = M.regions_from_diff(diff)[:4]
        ref.frames[i].save(vdir / f"{i:02d}-original.png")
        clone_frame.save(vdir / f"{i:02d}-clone.png")
        M.heatmap(ref.frames[i], diff).save(vdir / f"{i:02d}-diff.png")
        frames_info.append({"index": i, "scroll_y": y, "match": round(content * 100, 1),
                            "raw": round(raw * 100, 1),
                            "regions": [{"x": r[0], "y": y + r[1], "w": r[2], "h": r[3],
                                         "density": round(r[4], 2)} for r in regions]})

    mean_c = sum(contents) / len(contents)
    visual = 0.7 * mean_c + 0.3 * min(contents)

    el_scores, el_issues = M.compare_elements(vp, ref, clone)
    structure = M.structure_table(M.match_elements(ref.elements, clone.elements)[0], ref.width)
    asset_score, asset_issues = M.compare_assets(vp, ref, clone)
    motion_score, motion_issues = M.compare_motion(vp, ref.frames, clone.frames)

    issues: list[M.Issue] = el_issues + asset_issues + motion_issues
    # visual regions: tie the worst blobs to the element under them
    for f in frames_info:
        for reg in f["regions"][:2]:
            if reg["density"] < 0.12:
                continue
            under = [e for e in ref.elements
                     if e["x"] < reg["x"] + reg["w"] and e["x"] + e["w"] > reg["x"]
                     and e["y"] < reg["y"] + reg["h"] and e["y"] + e["h"] > reg["y"] and not e["fixed"]]
            under.sort(key=lambda e: e["w"] * e["h"])
            who = under[0]["path"] if under else ""
            issues.append(M.Issue(
                "visual", min(1.0, 0.2 + reg["density"] * 0.8 * min(1.0, reg["w"] * reg["h"] / (ref.width * 600))),
                vp, f'pixels differ in a {reg["w"]}x{reg["h"]}px area at y={reg["y"]}'
                + (f' (around `{who}`)' if who else ""), who,
                {"frame": f["index"], "x": reg["x"], "y": reg["y"], "w": reg["w"], "h": reg["h"],
                 "density": reg["density"]}))

    if ref.page_height and abs(clone.page_height - ref.page_height) > max(24, ref.page_height * 0.01):
        d = clone.page_height - ref.page_height
        issues.append(M.Issue("height", min(1.0, 0.3 + abs(d) / ref.page_height), vp,
                              f"page is {abs(d)}px {'taller' if d > 0 else 'shorter'} than the original "
                              f"({clone.page_height}px vs {ref.page_height}px)", "",
                              {"reference": ref.page_height, "clone": clone.page_height}))

    # a taller/shorter page is a layout problem even when the frames line up
    height_ratio = min(ref.page_height, clone.page_height) / max(ref.page_height, clone.page_height, 1)
    scores = {"visual": visual, "layout": el_scores["layout"] * (0.5 + 0.5 * height_ratio),
              "style": el_scores["style"], "content": el_scores["content"],
              "assets": asset_score, "motion": motion_score}
    return ViewportResult(
        name=vp, scores=scores, pixel_match_raw=sum(raws) / len(raws),
        ref_height=ref.page_height, clone_height=clone.page_height,
        noise_pct=(sum(noise_cells) / len(noise_cells) * 100) if noise_cells else 0.0,
        frames=frames_info, issues=issues, structure=structure)


async def compare_async(reference: str, clone: str, out_dir: Path, *, viewports=("desktop", "tablet", "mobile"),
                        wait_ms: int = 2500, settle_ms: int = 900, noise: bool = True, max_frames: int = 24,
                        say: Callable[[str], None] = lambda s: None, headers: dict | None = None,
                        headed: bool = False, channel: str | None = None, parallel: bool = True) -> Result:
    from playwright.async_api import async_playwright

    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, ViewportResult] = {}
    async with async_playwright() as pw:
        opts: dict = {"args": ["--use-gl=swiftshader", "--hide-scrollbars", "--force-color-profile=srgb", *LAUNCH_ARGS],
                      "headless": not headed}
        if channel:
            opts["channel"] = channel
        browser = await pw.chromium.launch(**opts)
        async def run(vp: str) -> ViewportResult:
            return await _one_viewport(
                browser, vp, reference, clone, out_dir, wait_ms=wait_ms, settle_ms=settle_ms,
                noise=noise, max_frames=max_frames, say=say, headers=headers)
        try:
            if parallel and len(viewports) > 1:
                done = await asyncio.gather(*(run(vp) for vp in viewports))
                results = dict(zip(viewports, done))
            else:
                for vp in viewports:
                    results[vp] = await run(vp)
        finally:
            await browser.close()
    return Result(reference, clone, results, time.time() - t0, out_dir)


def compare(reference: str, clone: str, out_dir: str | Path, **kw) -> Result:
    return asyncio.run(compare_async(reference, clone, Path(out_dir), **kw))


def save_json(result: Result, path: Path) -> None:
    path.write_text(json.dumps(result.to_dict(max_issues=400), indent=2, ensure_ascii=False), encoding="utf-8")
