"""cloneproof command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__

DEFAULT_OUT = ".cloneproof/latest"


def _say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _resolve(target: str, servers: list):
    """A directory becomes a served http://127.0.0.1:port URL; anything else is used as is."""
    p = Path(target).expanduser()
    if "://" not in target and p.is_dir():
        from .serve import serve
        srv, port = serve(p)
        servers.append(srv)
        return f"http://127.0.0.1:{port}/", str(p)
    if "://" not in target:
        target = "https://" + target
    return target, ""


def _browser_kw(a: argparse.Namespace) -> dict:
    headers = {}
    for h in a.header:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    return {"headers": headers or None, "headed": a.headed, "channel": "chrome" if a.chrome else None,
            "parallel": not a.serial}


def cmd_compare(a: argparse.Namespace) -> int:
    from .compare import compare
    from .prompt import build_prompt
    from .report import write_all

    servers: list = []
    ref, _ = _resolve(a.reference, servers)
    clone, hint = _resolve(a.clone, servers)
    vps = ("desktop",) if a.quick else tuple(v.strip() for v in a.viewports.split(","))
    out = Path(a.out)
    res = compare(ref, clone, out, viewports=vps, wait_ms=a.wait, settle_ms=a.settle,
                  noise=not (a.quick or a.no_noise), max_frames=a.frames, say=_say, **_browser_kw(a))
    prompt = build_prompt(res, target=a.target, clone_hint=hint, ref_arg=a.reference, clone_arg=a.clone)
    write_all(res, prompt)
    for s in servers:
        s.shutdown()
    if a.json:
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
    else:
        d = res.to_dict()
        print(f"\nscore {d['score']} / 100  ({d['verdict']})")
        for n, v in d["viewports"].items():
            c = v["categories"]
            print(f"  {n:<8}{v['score']:>6}   visual {c['visual']:.0f}  layout {c['layout']:.0f}  style {c['style']:.0f}"
                  f"  content {c['content']:.0f}  assets {c['assets']:.0f}  motion {c['motion']:.0f}")
        from .prompt import dedupe
        print("\nbiggest differences:")
        for i in dedupe(res.issues())[:8]:
            print(f"  [{i.viewport}] {i.summary}")
        print(f"\nreport   : {out}/report.html\nprompt   : {out}/prompt.md   (give it to your agent)"
              f"\nscorecard: {out}/scorecard.png")
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    if a.open:
        import webbrowser
        webbrowser.open((out / "report.html").resolve().as_uri())
    return 0 if res.score >= a.target else 1


def cmd_capture(a: argparse.Namespace) -> int:
    from .capture import capture
    url = a.url if "://" in a.url else "https://" + a.url
    print("note: only mirror sites you own or have permission to copy. Content belongs to its authors.",
          file=sys.stderr)
    info = capture(url, a.out, wait_ms=a.wait, say=_say, heal_rounds=0 if a.no_heal else 3)
    print(f"{info['files']} files, {info['bytes'] // 1024} KB -> {a.out}  (start page: {info['start']})")
    if info["skipped"]:
        print(f"skipped (too large): {len(info['skipped'])}")
    print(f"serve it: cloneproof serve {a.out}")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    from .serve import serve
    import time
    srv, port = serve(a.dir, a.port)
    print(f"serving {a.dir} on http://127.0.0.1:{port}/  (ctrl-c to stop)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


def cmd_loop(a: argparse.Namespace) -> int:
    from .loop import run_loop
    servers: list = []
    ref, _ = _resolve(a.reference, servers)
    clone, hint = _resolve(a.clone, servers)
    vps = ("desktop",) if a.quick else tuple(v.strip() for v in a.viewports.split(","))
    summary = run_loop(ref, clone, agent=a.agent, target=a.target, rounds=a.rounds, out=Path(a.out),
                       cwd=Path(a.cwd), hint=hint, ref_arg=a.reference, clone_arg=a.clone,
                       compare_kw=dict(viewports=vps, wait_ms=a.wait, settle_ms=a.settle,
                                       noise=not (a.quick or a.no_noise), max_frames=a.frames, **_browser_kw(a)))
    for s in servers:
        s.shutdown()
    print(json.dumps(summary))
    return 0 if summary["reached"] else 1


def cmd_init_agent(a: argparse.Namespace) -> int:
    from importlib import resources
    root = Path(a.dir).expanduser()
    skill = resources.files("cloneproof").joinpath("data/SKILL.md").read_text()
    for sub in (".claude/skills/cloneproof", ".agents/skills/cloneproof"):
        d = root / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(skill)
        print(f"wrote {d / 'SKILL.md'}")
    snippet = resources.files("cloneproof").joinpath("data/AGENTS-snippet.md").read_text()
    agents = root / "AGENTS.md"
    old = agents.read_text() if agents.exists() else ""
    if "cloneproof" not in old:
        agents.write_text((old + "\n\n" if old else "") + snippet)
        print(f"added cloneproof section to {agents}")
    claude = root / "CLAUDE.md"
    if not claude.exists():
        claude.write_text("@AGENTS.md\n")
        print(f"wrote {claude}")
    return 0


def cmd_doctor(a: argparse.Namespace) -> int:
    import asyncio
    from playwright.async_api import async_playwright

    async def go() -> str:
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            v = b.version
            await b.close()
            return v
    try:
        print("chromium ok:", asyncio.run(go()))
        return 0
    except Exception as e:
        print("chromium missing or broken:", str(e)[:200])
        print("fix: python -m playwright install chromium")
        return 1


def cmd_mcp(a: argparse.Namespace) -> int:
    from .mcp_server import main as mcp_main
    return mcp_main()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cloneproof", description="Measure how close a website clone is to the original.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--viewports", default="desktop,tablet,mobile")
        sp.add_argument("--quick", action="store_true", help="desktop only, no noise calibration (fast)")
        sp.add_argument("--no-noise", action="store_true")
        sp.add_argument("--wait", type=int, default=2500, help="ms to wait after load (preloaders)")
        sp.add_argument("--settle", type=int, default=900, help="ms to wait after each scroll")
        sp.add_argument("--frames", type=int, default=24)
        sp.add_argument("--target", type=float, default=97.0)
        sp.add_argument("--header", action="append", default=[], metavar="'Name: value'",
                        help="extra HTTP header for both sites (cookies, auth); repeatable")
        sp.add_argument("--headed", action="store_true", help="show the browser (helps with some bot walls)")
        sp.add_argument("--serial", action="store_true", help="measure the viewports one after another (slower, gentler on weak machines)")
        sp.add_argument("--chrome", action="store_true", help="use your installed Google Chrome instead of Chromium")

    c = sub.add_parser("compare", help="measure clone against reference")
    c.add_argument("reference", help="URL or folder of the original")
    c.add_argument("clone", help="URL or folder of the clone")
    c.add_argument("--out", default=DEFAULT_OUT)
    c.add_argument("--json", action="store_true", help="print the full result as JSON on stdout")
    c.add_argument("--open", action="store_true")
    common(c)
    c.set_defaults(fn=cmd_compare)

    cp = sub.add_parser("capture", help="mirror a site to a folder (own sites / permitted use)")
    cp.add_argument("url")
    cp.add_argument("--out", default="site-mirror")
    cp.add_argument("--wait", type=int, default=6000)
    cp.add_argument("--no-heal", action="store_true", help="skip the pass that fetches files the mirror still misses")
    cp.set_defaults(fn=cmd_capture)

    s = sub.add_parser("serve", help="serve a folder with Range support")
    s.add_argument("dir")
    s.add_argument("--port", type=int, default=4400)
    s.set_defaults(fn=cmd_serve)

    lp = sub.add_parser("loop", help="measure -> agent fixes -> measure, until the target is reached")
    lp.add_argument("reference")
    lp.add_argument("clone")
    lp.add_argument("--agent", required=True,
                    help='command that reads the prompt on stdin, e.g. "claude -p --permission-mode acceptEdits"')
    lp.add_argument("--rounds", type=int, default=6)
    lp.add_argument("--cwd", default=".", help="project folder the agent works in")
    lp.add_argument("--out", default=".cloneproof")
    common(lp)
    lp.set_defaults(fn=cmd_loop)

    ia = sub.add_parser("init-agent", help="teach Claude Code / Codex / Cursor to use cloneproof")
    ia.add_argument("--dir", default=".")
    ia.set_defaults(fn=cmd_init_agent)

    sub.add_parser("doctor", help="check the browser").set_defaults(fn=cmd_doctor)
    sub.add_parser("mcp", help="run as an MCP server (stdio)").set_defaults(fn=cmd_mcp)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
