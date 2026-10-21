"""Fast tests that need no browser."""

import numpy as np
from PIL import Image, ImageDraw

from cloneproof import measure as M
from cloneproof.capture import Mirror, local_path


def test_relative_and_entity_urls_are_rewritten():
    m = Mirror("https://x.com/", "/tmp/unused")
    m.add("https://x.com/", "text/html", b"<html></html>")
    m.add("https://x.com/news.css?v=3", "text/css", b"a{}")
    m.add("https://x.com/w/load.php?lang=en&skin=x", "text/css", b"b{}")
    m.add("https://x.com/a/b.png", "image/png", b"1")
    html = ('<link href="news.css?v=3"><link href="/w/load.php?lang=en&amp;skin=x">'
            "<img src='/a/b.png'>")
    out = m.rewrite(html, "index.html")
    assert "news.css?v=3" not in out and "load.php?" not in out and "/a/b.png" not in out
    assert "a/b.png" in out


def test_nested_file_gets_relative_prefix():
    m = Mirror("https://x.com/", "/tmp/unused")
    m.add("https://x.com/", "text/html", b"")
    m.add("https://x.com/css/site.css", "text/css", b"")
    m.add("https://x.com/img/z.jpg", "image/jpeg", b"1")
    assert "../img/z.jpg" in m.rewrite("a{background:url(/img/z.jpg)}", "css/site.css")


def test_extension_follows_content_type():
    assert local_path("https://fonts.googleapis.com/css2?family=Inter", "https://x.com/", "text/css").endswith(".css")
    assert local_path("https://x.com/_next/image?url=a", "https://x.com/", "image/webp").endswith(".webp")


def _page(shift=0, colour=(20, 20, 20)):
    img = Image.new("RGB", (400, 600), (250, 250, 250))
    d = ImageDraw.Draw(img)
    for i in range(8):
        d.rectangle((40, 40 + shift + i * 60, 360, 70 + shift + i * 60), fill=colour)
    return img


def test_identical_frames_match():
    raw, content, diff = M.frame_similarity(_page(), _page(), None)
    assert content > 0.999 and not diff.any()


def test_vertical_shift_is_forgiven_by_the_pixel_score():
    raw, content, _ = M.frame_similarity(_page(), _page(shift=12), None)
    assert raw < 0.9            # unaligned it is clearly different
    assert content > 0.9        # aligned, it looks the same


def test_colour_change_is_not_forgiven():
    _, content, diff = M.frame_similarity(_page(), _page(colour=(200, 30, 30)), None)
    assert content < 0.3 and diff.any()


def test_noise_mask_hides_changing_regions():
    a, b = _page(), _page()
    ImageDraw.Draw(b).rectangle((100, 100, 200, 140), fill=(0, 0, 255))
    mask = M.noise_mask(_page(), b)
    _, content, _ = M.frame_similarity(a, b, mask)
    assert content > 0.99


def test_large_shift_is_followed_by_the_alignment():
    # a section inserted above makes everything 150px lower; the pixels still look the same
    ref = _page()
    shifted = Image.new("RGB", (400, 750), (250, 250, 250))
    shifted.paste(_page(), (0, 150))
    cropped = shifted.crop((0, 0, 400, 600))
    # the clone shows the same content 150px lower, so compare the reference against a frame
    # that starts 150px earlier on the clone side
    raw, content, _ = M.frame_similarity(ref, shifted.crop((0, 0, 400, 600)), None)
    assert content > 0.6


def _el(tag, x, y, w, h, text="", fs="16px", lh="20px", **kw):
    return {"tag": tag, "path": f"{tag}.x", "text": text, "x": x, "y": y, "w": w, "h": h, "media": tag in ("img", "svg"),
            "fixed": False, "s": {"fontSize": fs, "lineHeight": lh, "fontFamily": "A", "fontWeight": "400", "letterSpacing": "normal",
                                  "color": "rgb(0,0,0)", "background": "rgba(0,0,0,0)", "borderRadius": "0px", "opacity": "1",
                                  "textAlign": "left", "textTransform": "none", "backgroundImage": "", "boxShadow": "",
                                  "borderTopWidth": "0px", "borderTopColor": "rgb(0,0,0)"}, **kw}


def test_slightly_bigger_illustration_is_a_size_issue_not_missing_plus_extra():
    from cloneproof.probe import Probe
    ref = Probe(url="a", viewport="desktop", width=1440, height=900, elements=[_el("svg", 100, 100, 300, 300)])
    clone = Probe(url="b", viewport="desktop", width=1440, height=900, elements=[_el("svg", 100, 100, 340, 330)])
    _, issues = M.compare_elements("desktop", ref, clone)
    kinds = [i.kind for i in issues]
    assert "missing" not in kinds and "extra" not in kinds and "size" in kinds


def test_size_issue_explains_text_wrapping():
    from cloneproof.probe import Probe
    ref = Probe(url="a", viewport="desktop", width=1440, height=900,
                elements=[_el("p", 0, 0, 600, 40, text="hello world again and again")])
    clone = Probe(url="b", viewport="desktop", width=1440, height=900,
                  elements=[_el("p", 0, 0, 400, 80, text="hello world again and again")])
    _, issues = M.compare_elements("desktop", ref, clone)
    size = next(i for i in issues if i.kind == "size")
    assert "wraps to 4 lines" in size.summary and "original to 2" in size.summary


def test_badge_is_valid_svg_with_the_score():
    import xml.etree.ElementTree as ET
    from cloneproof.report import badge_svg
    svg = badge_svg(96.6)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg") and "96.6 / 100" in svg
    assert "#22c55e" not in badge_svg(70.0) and "#22c55e" in badge_svg(99.0)


def test_verify_mirror_flags_a_blank_mirror(tmp_path):
    import asyncio
    from cloneproof.capture import verify_mirror
    (tmp_path / "index.html").write_text("<html><body></body></html>")
    r = asyncio.run(verify_mirror(tmp_path, "index.html", live_text=2000))
    assert r["ok"] is False
    (tmp_path / "index.html").write_text("<html><body>" + "hello world " * 200 + "</body></html>")
    assert asyncio.run(verify_mirror(tmp_path, "index.html", live_text=2400))["ok"] is True


def test_javascript_strings_that_look_like_paths_are_left_alone():
    """figma.com: "/." and "../" inside a JS bundle resolved to the start page and became ../../index.html,
    which broke the script and left the whole site blank."""
    m = Mirror("https://x.test/", "/tmp/unused")
    m.add("https://x.test/", "text/html", b"<html></html>")
    m.add("https://x.test/_next/static/chunks/app.js", "javascript", b"1")
    m.add("https://x.test/_next/static/chunks/chunk-abc.js", "javascript", b"1")
    js = 'var a="/.",b="../",c=".//",d="./chunk-abc.js";'
    out = m.rewrite(js, "_next/static/chunks/app.js")
    assert 'a="/."' in out and 'b="../"' in out and 'c=".//"' in out and "index.html" not in out, out
    assert "chunk-abc.js" in out.split('d="')[1]


def test_sourcemap_comment_is_left_alone():
    m = Mirror("https://x.test/", "/tmp/unused")
    m.add("https://x.test/", "text/html", b"<html></html>")
    m.add("https://x.test/assets/app.js", "javascript", b"1")
    js = "let a=1;\n//# sourceMappingURL=app.js.map\n"
    assert m.rewrite(js, "assets/app.js") == js
    m.add("https://cdn.test/lib.js", "javascript", b"1")
    assert "//cdn.test" not in m.rewrite('<script src="//cdn.test/lib.js"></script>', "index.html")


def test_cdn_folder_url_points_to_the_local_folder():
    m = Mirror("https://x.test/", "/tmp/unused")
    m.add("https://x.test/", "text/html", b"<html></html>")
    m.add("https://cdn.test/assets/app.js", "javascript", b"1")
    m.add("https://cdn.test/assets/vendor.js", "javascript", b"1")
    out = m.rewrite('n.p="https://cdn.test/assets/";', "_ext/cdn.test/assets/app.js")
    assert 'n.p="/_ext/cdn.test/assets/"' in out, out


def test_integrity_attributes_are_removed_from_mirrored_html(tmp_path):
    m = Mirror("https://x.test/", tmp_path)
    html = ('<html><head><script src="https://x.test/a.js" integrity="sha384-abc" crossorigin="anonymous"></script></head>'
            "<body><script>\n// note\nvar a=1;\n</script></body></html>")
    m.add("https://x.test/", "text/html", html.encode())
    m.add("https://x.test/a.js", "javascript", b"1")
    m.write()
    out = (tmp_path / "index.html").read_text()
    assert "integrity=" not in out and "// note" in out, out
