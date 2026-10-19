"""A tiny static file server with HTTP Range support (browsers need it for video)."""

from __future__ import annotations

import mimetypes
import os
import re
import socketserver
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")


class _Handler(SimpleHTTPRequestHandler):
    root: Path = Path(".")
    spa: bool = True

    def log_message(self, *a):  # quiet
        pass

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        rel = os.path.normpath(path.lstrip("/"))
        full = (self.root / rel).resolve()
        if not str(full).startswith(str(self.root.resolve())):
            return str(self.root / "index.html")
        if full.is_dir():
            idx = full / "index.html"
            return str(idx if idx.exists() else full)
        if not full.exists() and self.spa and not Path(rel).suffix:
            return str(self.root / "index.html")
        return str(full)

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if not m:
            return super().send_head()
        size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else max(size - int(m.group(2) or 0), 0)
        end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._left = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            chunk = source.read(min(65536, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)
        self._left = None

    def guess_type(self, path):
        t = super().guess_type(path)
        if t.startswith("text/") or t in ("application/javascript", "application/json"):
            return t + "; charset=utf-8"
        return t

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):   # browsers abort requests all the time
        import sys
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def serve(directory: str | Path, port: int = 0, spa: bool = True) -> tuple[_Server, int]:
    """Start serving `directory` in a background thread. Returns (server, port)."""
    handler = type("H", (_Handler,), {"root": Path(directory).resolve(), "spa": spa})
    srv = _Server(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]
