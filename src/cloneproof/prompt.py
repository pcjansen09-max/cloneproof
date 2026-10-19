"""Build the prompt that sends an AI coding agent back to work on the clone."""

from __future__ import annotations

from pathlib import Path

from .compare import Result, verdict
from . import measure as M

KIND_ORDER = ["missing", "height", "position", "size", "style", "font", "text", "visual", "motion", "asset", "console", "extra"]


def _group(issues: list[M.Issue]) -> dict[str, list[M.Issue]]:
    out: dict[str, list[M.Issue]] = {}
    for i in issues:
        out.setdefault(i.kind, []).append(i)
    return out


def dedupe(issues: list[M.Issue]) -> list[M.Issue]:
    """The same element often shows up at three viewports; keep the worst of each."""
    seen: dict[tuple, M.Issue] = {}
    for i in issues:
        key = (i.kind, i.selector or i.summary[:60], i.detail.get("property", ""))
        if key not in seen or i.severity > seen[key].severity:
            seen[key] = i
    return sorted(seen.values(), key=lambda i: i.severity, reverse=True)


def build_prompt(result: Result, target: float = 97.0, limit: int = 25, clone_hint: str = "",
                 round_no: int | None = None) -> str:
    d = result.to_dict()
    top = dedupe(result.issues())[:limit]
    lines = [
        "You are fixing a website clone so that it is visually and behaviourally 1:1 with the original.",
        "",
        f"Original : {result.reference}",
        f"Clone    : {result.clone}" + (f"   (source: {clone_hint})" if clone_hint else ""),
        f"Score    : {d['score']} / 100 ({d['verdict']}). Target: {target:g}."
        + (f" This is round {round_no}." if round_no else ""),
        "Per viewport: " + ", ".join(f"{n} {v['score']}" for n, v in d["viewports"].items()),
        "",
        "How to work",
        "1. Fix the differences below, biggest first. They are measured, not opinions: every line is a "
        "difference between computed styles / boxes / pixels of the real original and your clone.",
        "2. Change the clone's SOURCE CODE (HTML/CSS/JS/components). Never patch a screenshot in, never "
        "hotlink the original's assets, never special-case the measurement.",
        "3. After a batch of fixes, re-measure with:",
        f"       cloneproof compare {result.reference} {result.clone} --json --target {target:g}",
        "   Exit code 0 means the target is reached. Stop when it is, or when two rounds in a row do not "
        "improve the score.",
        f"4. Look at the images when a line is unclear: {result.out_dir}/<viewport>/NN-original.png, "
        "NN-clone.png and NN-diff.png (red = different).",
        "",
        "Differences, most visible first",
    ]
    for n, i in enumerate(top, 1):
        vp = f"[{i.viewport}] "
        lines.append(f"{n:>2}. {vp}{i.summary}")
        if i.kind == "style":
            lines.append(f"      fix: set `{i.detail['property']}: {i.detail['original']}` on `{i.selector}`")
        elif i.kind == "position":
            lines.append(f"      the original box starts at x={i.detail['ref_x']:.0f}, y={i.detail['ref_y']:.0f}")
        elif i.kind == "size":
            lines.append(f"      target size {i.detail['ref_w']:.0f}x{i.detail['ref_h']:.0f}px")
        elif i.kind == "visual":
            lines.append(f"      see {result.out_dir}/{i.viewport}/{i.detail['frame']:02d}-diff.png")
    if len(dedupe(result.issues())) > limit:
        lines.append(f"    ... and {len(dedupe(result.issues())) - limit} smaller differences (see report.json)")
    low = [n for n, v in d["viewports"].items() if v["score"] < 85]
    if low:
        lines += ["", f"Weakest viewport(s): {', '.join(low)}. Check responsive rules (media queries, "
                      "clamp(), container widths) before chasing single pixels."]
    cats = {}
    for n, v in d["viewports"].items():
        for k, x in v["categories"].items():
            cats.setdefault(k, []).append(x)
    weakest = sorted(((sum(v) / len(v), k) for k, v in cats.items()))[:2]
    lines += ["", "Weakest categories: " + ", ".join(f"{k} {s:.0f}" for s, k in weakest)]
    return "\n".join(lines) + "\n"


def write_prompt(result: Result, path: Path, **kw) -> str:
    text = build_prompt(result, **kw)
    path.write_text(text)
    return text
