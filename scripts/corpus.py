"""Stress test: mirror real sites, then measure the mirror against the live site.

A perfect tool + a perfect mirror would score ~100. Anything lower is either a capture
weakness or a measurement weakness; the issue list says which.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from cloneproof.capture import capture
from cloneproof.compare import compare
from cloneproof.serve import serve

SITES = {
    "example": "https://example.com",
    "hn": "https://news.ycombinator.com",
    "wikipedia": "https://en.wikipedia.org/wiki/Cascading_Style_Sheets",
    "tailwind": "https://tailwindcss.com",
    "vercel": "https://vercel.com",
    "resend": "https://resend.com",
    "linear": "https://linear.app",
    "wordpress": "https://wordpress.org",
    "framer": "https://www.framer.com",
    "threejs": "https://threejs.org",
    "bruno": "https://bruno-simon.com",
    "deltadesign": "https://delta-design.nl",
    "bedrijfsstack": "https://bedrijfsstack.nl",
    "stripe": "https://stripe.com",
}

if __name__ == "__main__":
    which = sys.argv[1:] or list(SITES)
    base = Path("corpus")
    base.mkdir(exist_ok=True)
    log = base / "results.jsonl"
    for name in which:
        url = SITES[name]
        row = {"name": name, "url": url}
        t0 = time.time()
        try:
            info = capture(url, base / name / "mirror", wait_ms=5000)
            row["capture"] = {k: info[k] for k in ("files", "bytes", "start")}
            srv, port = serve(base / name / "mirror")
            try:
                res = compare(url, f"http://127.0.0.1:{port}/{info['start']}" if info["start"] not in ("index.html", "") else f"http://127.0.0.1:{port}/",
                              base / name / "report", viewports=("desktop", "mobile"), wait_ms=3500, settle_ms=800, max_frames=14)
            finally:
                srv.shutdown()
            from cloneproof.report import write_all
            from cloneproof.prompt import build_prompt
            write_all(res, build_prompt(res))
            d = res.to_dict(max_issues=15)
            row.update(score=d["score"], viewports={k: v["score"] for k, v in d["viewports"].items()},
                       categories=d["viewports"]["desktop"]["categories"],
                       issues=[i["summary"] for i in d["issues"][:10]])
        except Exception as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        row["seconds"] = round(time.time() - t0)
        with log.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(name, row.get("score"), row.get("error", ""), flush=True)
