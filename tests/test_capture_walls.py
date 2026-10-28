"""Things found by running the SuusOS copier on 33 real sites, ported to cloneproof capture."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cloneproof.capture import Mirror, capture


def test_bare_file_name_in_code_is_left_alone():
    """github.com (webpack): i.p+"tile.webp" glues a file name behind a base path; turning it into a path relative to the
    JS file gives base + "../../../_ext/..": hundreds of 404s."""
    m = Mirror("https://x.com/", "/tmp/unused")
    m.add("https://x.com/", "text/html", b"<html></html>")
    m.add("https://cdn.test/assets/app.js", "javascript", b"1")
    m.add("https://cdn.test/assets/tile-1-abc.webp", "image/webp", b"1")
    m.add("https://cdn.test/assets/tile-2-abc.webp", "image/webp", b"1")
    out = m.rewrite('let a=i.p+"tile-1-abc.webp",b=i.p+"tile-2-abc.webp"', "_ext/cdn.test/assets/app.js")
    assert 'i.p+"tile-1-abc.webp"' in out and 'i.p+"tile-2-abc.webp"' in out, out


def test_css_variable_url_in_html_is_root_absolute():
    """A url() inside a CSS custom property resolves against the stylesheet that USES the variable, not the page."""
    m = Mirror("https://x.com/", "/tmp/unused")
    m.add("https://x.com/", "text/html", b"<html></html>")
    m.add("https://cdn.test/assets/tile-1.webp", "image/webp", b"1")
    html = '<div style="--color:url(https://cdn.test/assets/tile-1.webp)"></div><img src="https://cdn.test/assets/tile-1.webp">'
    out = m.rewrite(html, "index.html")
    assert "--color:url(/_ext/cdn.test/assets/tile-1.webp)" in out, out
    assert 'src="./_ext/cdn.test/assets/tile-1.webp"' in out, out


def test_consent_wall_is_clicked_away(tmp_path):
    """nu.nl style: no cookie means a redirect to a consent page; the 'copy' used to be that page."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            ok = "toestemming=ja" in (self.headers.get("Cookie") or "")
            if self.path == "/accept":
                self.send_response(302)
                self.send_header("Set-Cookie", "toestemming=ja; Path=/")
                self.send_header("Location", "/")
                self.end_headers()
            elif self.path == "/" and not ok:
                self.send_response(302)
                self.send_header("Location", "/consent?callback=/")
                self.end_headers()
            elif self.path.startswith("/consent"):
                self._html("<html><body><div><p>We use cookies and your privacy matters.</p>"
                           "<button onclick=\"location='/accept'\">Accept all</button><button>Settings</button></div></body></html>")
            else:
                self._html("<html><head><title>Real site</title></head><body><h1>REAL SITE</h1>" + "<p>content</p>" * 30 + "</body></html>")

        def _html(self, text):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(text.encode())

        def log_message(self, *_):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        info = capture(f"http://127.0.0.1:{srv.server_address[1]}/", tmp_path / "out", wait_ms=500, heal_rounds=0)
    finally:
        srv.shutdown()
    html = (Path(tmp_path / "out") / info["start"]).read_text(encoding="utf-8")
    assert "REAL SITE" in html and "Accept all" not in html, html[:300]
