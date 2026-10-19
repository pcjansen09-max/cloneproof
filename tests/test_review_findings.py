"""Regression tests for the problems an independent review (Codex) found. Each one failed before the fix."""

import json
from pathlib import Path

import pytest
from PIL import Image

from cloneproof import measure as M
from cloneproof.capture import Mirror, local_path
from cloneproof.loop import restore, snapshot
from cloneproof.probe import Probe, plan_positions
from cloneproof.serve import serve


def test_mirror_never_writes_outside_its_folder(tmp_path):
    out = tmp_path / "mirror"
    m = Mirror("https://x.test/", out)
    m.add("https://x.test/", "text/html", b"<html></html>")
    m.add("https://x.test/..%2Fimportant.txt", "text/plain", b"replaced")
    m.add("https://x.test/a/../../escape.txt", "text/plain", b"replaced")
    m.write()
    assert not (tmp_path / "important.txt").exists()
    assert not (tmp_path / "escape.txt").exists()
    assert all(str(p.resolve()).startswith(str(out.resolve())) for p in out.rglob("*"))


def test_local_path_has_no_parent_segments():
    assert ".." not in Path(local_path("https://x.test/a/%2e%2e/%2e%2e/b.txt", "https://x.test/", "text/plain")).parts


def test_restore_keeps_nested_git_and_node_modules(tmp_path):
    proj = tmp_path / "proj"
    (proj / "packages/app/.git").mkdir(parents=True)
    (proj / "packages/app/.git/HEAD").write_text("ref")
    (proj / "packages/app/src.txt").write_text("v1")
    (proj / "node_modules/x").mkdir(parents=True)
    (proj / "node_modules/x/i.js").write_text("1")
    snap = tmp_path / "snap"
    snapshot(proj, snap)
    (proj / "packages/app/src.txt").write_text("v2-worse")
    (proj / "packages/app/new.txt").write_text("added by agent")
    restore(snap, proj)
    assert (proj / "packages/app/.git/HEAD").read_text() == "ref"
    assert (proj / "packages/app/src.txt").read_text() == "v1"
    assert not (proj / "packages/app/new.txt").exists()
    assert (proj / "node_modules/x/i.js").exists()


def test_snapshot_does_not_copy_itself(tmp_path):
    proj = tmp_path / "proj"
    (proj / "out").mkdir(parents=True)
    (proj / "index.html").write_text("x")
    snapshot(proj, proj / "out" / "best", exclude=proj / "out")
    assert not (proj / "out" / "best" / "out").exists()
    assert (proj / "out" / "best" / "index.html").exists()


def test_server_blocks_sibling_directory_with_same_prefix(tmp_path):
    import urllib.request
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("ok")
    (tmp_path / "site-private").mkdir()
    (tmp_path / "site-private" / "secret.txt").write_text("SECRET")
    srv, port = serve(tmp_path / "site")
    try:
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", port)
        c.request("GET", "/../site-private/secret.txt")
        body = c.getresponse().read()
    finally:
        srv.shutdown()
    assert b"SECRET" not in body


def test_server_decodes_percent_encoded_names(tmp_path):
    import urllib.request
    (tmp_path / "my photo.png").write_bytes(b"PNGDATA")
    (tmp_path / "index.html").write_text("ok")
    srv, port = serve(tmp_path)
    try:
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/my%20photo.png").read()
    finally:
        srv.shutdown()
    assert body == b"PNGDATA"


def _probe(elements):
    return Probe(url="x", viewport="desktop", width=1440, height=900, elements=elements)


def test_two_identical_empty_pages_have_full_layout_score():
    scores, issues = M.compare_elements("desktop", _probe([]), _probe([]))
    assert scores["layout"] == 1.0 and not issues


def test_missing_solid_area_counts_against_content_score():
    white_tall = Image.new("RGB", (100, 100), (255, 255, 255))
    white_short = Image.new("RGB", (100, 50), (255, 255, 255))
    raw, content, _ = M.frame_similarity(white_tall, white_short, None)
    assert content < 0.9


def test_single_frame_plan_does_not_divide_by_zero():
    assert plan_positions(1800, 900, 1) == [0]


def test_write_all_writes_prompt_md_and_utf8(tmp_path):
    from cloneproof.compare import Result, ViewportResult
    from cloneproof.report import write_all
    vr = ViewportResult("desktop", {k: 1.0 for k in ("visual", "layout", "style", "content", "assets", "motion")},
                        1.0, 100, 100, 0.0, frames=[], issues=[M.Issue("text", 0.5, "desktop", "text differs: 你好 vs 世界")])
    res = Result("http://a", "http://b", {"desktop": vr}, 1.0, tmp_path)
    write_all(res, "prompt 你好")
    assert (tmp_path / "prompt.md").read_text(encoding="utf-8") == "prompt 你好"
    assert "你好" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_copied_files_are_detected(tmp_path):
    from cloneproof.loop import find_copies
    orig, clone = tmp_path / "o", tmp_path / "c"
    orig.mkdir(); clone.mkdir()
    big = "<html>" + "x" * 500 + "</html>"
    (orig / "index.html").write_text(big)
    (orig / "style.css").write_text("a{}" * 200)
    (clone / "index.html").write_text(big)                 # pasted from the original
    (clone / "style.css").write_text("b{}" * 200)          # written by the agent
    (clone / "tiny.txt").write_text("hi")
    assert find_copies(orig, clone) == ["index.html"]
