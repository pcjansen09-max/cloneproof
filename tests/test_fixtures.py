"""End-to-end checks on small local pages: the score must be honest in both directions."""

import shutil
from pathlib import Path

import pytest

from cloneproof.compare import compare
from cloneproof.serve import serve

FIX = Path(__file__).parent / "fixtures" / "ref"


@pytest.fixture(scope="module")
def servers():
    s, port = serve(FIX)
    yield s, port
    s.shutdown()


def variant(tmp_path: Path, name: str, *edits: tuple[str, str]) -> Path:
    d = tmp_path / name
    shutil.copytree(FIX, d)
    html = (d / "index.html").read_text()
    for a, b in edits:
        assert a in html, a
        html = html.replace(a, b)
    (d / "index.html").write_text(html)
    return d


def run(ref_port: int, folder: Path, out: Path, **kw):
    s, port = serve(folder)
    try:
        return compare(f"http://127.0.0.1:{ref_port}/", f"http://127.0.0.1:{port}/", out,
                       viewports=("desktop",), wait_ms=300, settle_ms=250, **kw)
    finally:
        s.shutdown()


def test_identical_site_scores_100(servers, tmp_path):
    _, port = servers
    d = tmp_path / "same"
    shutil.copytree(FIX, d)
    r = run(port, d, tmp_path / "o1")
    assert r.score >= 99.0, r.to_dict()["issues"][:5]


def test_font_size_change_is_found_by_name(servers, tmp_path):
    _, port = servers
    d = variant(tmp_path, "fs", ("font-size:64px", "font-size:48px"))
    r = run(port, d, tmp_path / "o2")
    kinds = {(i.kind, i.detail.get("property")) for i in r.issues()}
    assert ("style", "font-size") in kinds
    assert 60 < r.score < 99.5


def test_missing_element_and_text_change(servers, tmp_path):
    _, port = servers
    d = variant(tmp_path, "mt", ('<a href="#c">Contact</a>', ""), ("Fixed prices.", "Fixed price."))
    r = run(port, d, tmp_path / "o3")
    kinds = {i.kind for i in r.issues()}
    assert "missing" in kinds and "text" in kinds


def test_color_change_detected(servers, tmp_path):
    _, port = servers
    d = variant(tmp_path, "col", ("color:#4f46e5;padding:14px", "color:#e11d48;padding:14px"))
    r = run(port, d, tmp_path / "o4")
    assert any(i.kind == "style" and i.detail.get("property") == "color" for i in r.issues())


def test_noise_does_not_hurt_a_perfect_clone(tmp_path):
    """A page with a ticking counter still scores ~100 against itself thanks to the noise mask."""
    base = tmp_path / "tick"
    shutil.copytree(FIX, base)
    html = (base / "index.html").read_text().replace(
        "</body>", '<div id="t" style="position:absolute;top:30px;right:200px;color:#fff;font:20px monospace"></div>'
        "<script>setInterval(()=>{t.textContent=Date.now()%100000},37)</script></body>")
    (base / "index.html").write_text(html)
    other = tmp_path / "tick2"
    shutil.copytree(base, other)
    s, port = serve(base)
    try:
        r = run(port, other, tmp_path / "o5")
    finally:
        s.shutdown()
    assert r.score >= 97.0


def test_fix_prompt_mentions_the_fix(servers, tmp_path):
    from cloneproof.prompt import build_prompt
    _, port = servers
    d = variant(tmp_path, "fp", ("font-size:64px", "font-size:48px"))
    r = run(port, d, tmp_path / "o6")
    p = build_prompt(r)
    assert "font-size: 64px" in p and "cloneproof compare" in p
