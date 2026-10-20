"""Who mirrors a page best? Four tools, same pages, one judge (cloneproof compare).

For each site and tool: save the single page offline, serve the folder, measure it against the live site.
Run:  python scripts/showdown.py [site ...]     results go to showdown/results.jsonl
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from cloneproof.capture import capture
from cloneproof.compare import compare
from cloneproof.report import write_all
from cloneproof.prompt import build_prompt
from cloneproof.serve import serve

SITES = {
    "example": "https://example.com",
    "hackernews": "https://news.ycombinator.com",
    "wikipedia": "https://en.wikipedia.org/wiki/Cascading_Style_Sheets",
    "wordpress": "https://wordpress.org",
    "linear": "https://linear.app",
    "tailwind": "https://tailwindcss.com",
    "threejs": "https://threejs.org",
}
CHROME = next(Path.home().joinpath("Library/Caches/ms-playwright").glob("chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"), None) \
    or next(Path.home().joinpath("Library/Caches/ms-playwright").glob("chromium-*/chrome-mac*/*/Contents/MacOS/*"), None)
SINGLEFILE = Path("/tmp/sfcli/node_modules/.bin/single-file")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36"


def run_cmd(cmd, timeout=300):
    subprocess.run(cmd, capture_output=True, timeout=timeout)


def make(tool: str, url: str, out: Path) -> str:
    """Save the page with `tool` into `out`. Returns the path of the start file relative to out."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    host = url.split("//", 1)[1].split("/")[0]
    if tool == "cloneproof":
        info = capture(url, out, wait_ms=5000)
        return info["start"] or "index.html"
    if tool == "wget":
        run_cmd(["wget", "-E", "-H", "-k", "-K", "-p", "-e", "robots=off", "-U", UA, "--timeout=20", "--tries=2",
                 "-P", str(out), url])
        files = sorted(out.rglob("*.html"), key=lambda p: (len(p.parts), p.name))
        own = [p for p in files if host.replace("www.", "") in str(p)]
        return str((own or files)[0].relative_to(out))
    if tool == "httrack":
        run_cmd(["httrack", url, "-O", str(out), "-r2", "-n", "-%v0", "-s0", "-T20", "-c4", "--user-agent", UA, "-q"], 300)
        files = sorted((p for p in out.rglob("*.html")), key=lambda p: (len(p.parts), p.name))
        own = [p for p in files if host.replace("www.", "") in str(p.relative_to(out)) and p.name != "hts-cache"]
        return str((own or files)[0].relative_to(out)) if files else "index.html"
    if tool == "singlefile":
        run_cmd([str(SINGLEFILE), url, str(out / "index.html"), "--browser-executable-path", str(CHROME),
                 "--browser-wait-delay", "4000", "--browser-load-max-time", "90000",
                 "--browser-arg", '["--no-sandbox"]'], 300)
        return "index.html"
    raise ValueError(tool)


if __name__ == "__main__":
    which = sys.argv[1:] or list(SITES)
    base = Path("showdown")
    base.mkdir(exist_ok=True)
    log = base / "results.jsonl"
    for name in which:
        for tool in ("cloneproof", "singlefile", "httrack", "wget"):
            row = {"site": name, "tool": tool, "url": SITES[name]}
            t0 = time.time()
            try:
                start = make(tool, SITES[name], base / name / tool / "files")
                srv, port = serve(base / name / tool / "files")
                try:
                    res = compare(SITES[name], f"http://127.0.0.1:{port}/{start}", base / name / tool / "report",
                                  viewports=("desktop", "mobile"), wait_ms=3500, settle_ms=800, max_frames=12)
                finally:
                    srv.shutdown()
                write_all(res, build_prompt(res))
                d = res.to_dict(max_issues=8)
                row.update(score=d["score"], viewports={k: v["score"] for k, v in d["viewports"].items()},
                           issues=[i["summary"][:160] for i in d["issues"][:5]])
            except Exception as e:  # noqa: BLE001
                row["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            row["seconds"] = round(time.time() - t0)
            with log.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(name, tool, row.get("score"), row.get("error", ""), flush=True)
