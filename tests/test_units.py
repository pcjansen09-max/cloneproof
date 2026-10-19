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
