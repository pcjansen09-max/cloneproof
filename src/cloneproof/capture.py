"""Mirror a website so it runs offline: HTML, CSS, JS, fonts, images, video, 3D models.

This is a starting point for rebuilding a site you own or are allowed to copy, and a way to
get a stable local reference. It is not a publishing tool: content, images and fonts belong
to whoever made them.

What it does that a plain `wget --mirror` does not:
  * opens the page in a real browser and scrolls it top to bottom, so lazy-loaded images,
    scroll-triggered scripts and videos that only start in view are fetched too;
  * stores everything the browser actually asked for (including requests made by JavaScript);
  * downloads media in full (browsers ask for video in Range slices, which would give you a
    fragment);
  * gives every file the right extension for its content type (a stylesheet saved as .html
    is refused by the browser);
  * rewrites absolute URLs in HTML, CSS and JS to local paths, longest first and only where a
    URL really ends, so one URL can never eat the head of a longer one.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from .browser import LAUNCH_ARGS, normal_user_agent

KEEP = ("text/html", "text/css", "javascript", "font", "image", "video", "audio",
        "application/json", "octet-stream", "model/", "application/wasm", "text/plain", "xml")
MAX_BYTES = 80 * 1024 * 1024
TEXT_EXT = (".html", ".css", ".js", ".mjs", ".json", ".svg", ".xml", ".webmanifest")
MEDIA_EXT = (".mp4", ".webm", ".mov", ".m4v", ".ogg", ".mp3", ".wav", ".glb", ".gltf", ".mp4")
BOUNDARY = r'(?=["\'`)\s>,;\\]|$)'

EXT_BY_TYPE = {
    "text/html": ".html", "text/css": ".css", "javascript": ".js", "application/json": ".json",
    "image/svg": ".svg", "font/woff2": ".woff2", "font/woff": ".woff", "font/ttf": ".ttf",
    "font/otf": ".otf", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/avif": ".avif", "image/gif": ".gif", "video/mp4": ".mp4", "video/webm": ".webm",
    "model/gltf-binary": ".glb", "application/wasm": ".wasm",
}


def _short(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:6]


def local_path(url: str, origin: str, content_type: str = "") -> str:
    """Where a resource lives inside the mirror."""
    u = urlparse(url)
    path = unquote(u.path)
    want = next((e for k, e in EXT_BY_TYPE.items() if k in content_type), "")
    if path.endswith("/") or not path:
        path += "index" + (want or ".html")
    elif not Path(path).suffix:
        path += want or "/index.html"
    elif want and Path(path).suffix.lower() != want and want in (".css", ".js", ".json", ".svg"):
        path += want
    parts = [seg for seg in path.split("/") if seg not in ("", ".", "..")]   # never leave the mirror folder
    parts = [re.sub(r'[<>:"|?*\\\x00-\x1f]', "_", seg) for seg in parts]
    path = "/".join(parts)
    if u.query:                      # fonts.googleapis.com/css2?family=A and ?family=B differ
        stem, dot, ext = path.rpartition(".")
        tag = _short(u.query)
        path = f"{stem}-{tag}{dot}{ext}" if dot else f"{path}-{tag}"
    if u.netloc and u.netloc != urlparse(origin).netloc:
        return f"_ext/{u.netloc}/{path}"
    return path


def relative(src: str, dst: str) -> str:
    return "../" * src.count("/") + dst


class Mirror:
    def __init__(self, url: str, folder: Path) -> None:
        self.url, self.origin, self.folder = url, url, folder
        self.files: dict[str, bytes] = {}
        self.urls: dict[str, str] = {}
        self.source_of: dict[str, str] = {}
        self.ctypes: dict[str, str] = {}
        self.skipped: list[str] = []

    def add(self, url: str, content_type: str, body: bytes) -> None:
        if not any(k in content_type for k in KEEP):
            return
        if len(body) > MAX_BYTES:
            self.skipped.append(f"{url} ({len(body) // 2**20} MB)")
            return
        p = local_path(url, self.origin, content_type)
        self.ctypes[url.split("#")[0]] = content_type
        self.files.setdefault(p, body)
        self.urls[url.split("#")[0]] = p
        self.source_of.setdefault(p, url.split("#")[0])

    def rebase(self, new_origin: str) -> None:
        """The page lives on another host than we asked for (example.com -> www.example.com):
        move every file so that the host we ended up on is the site root."""
        old_files, old_urls = self.files, self.urls
        self.origin = new_origin
        self.files, self.urls, self.source_of = {}, {}, {}
        by_path = {p: u for u, p in old_urls.items()}
        for url, old_path in old_urls.items():
            p = local_path(url, new_origin, self.ctypes.get(url, ""))
            self.files.setdefault(p, old_files[old_path])
            self.urls[url] = p
            self.source_of.setdefault(p, url)

    def fetch_full_media_blocking(self) -> list[str]:
        done = []
        for url, p in list(self.urls.items()):
            if not p.lower().endswith(MEDIA_EXT):
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "cloneproof/0.1"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    whole = r.read()
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                continue
            if len(whole) > len(self.files.get(p, b"")):
                self.files[p] = whole
                done.append(p)
        return done

    TOKEN = re.compile(r"""(?P<q>["'(=\s,])(?P<u>[A-Za-z0-9_\-./:%@~+#?=&;!$*\[\]]{2,600})(?=["')\s,>]|$)""")

    def rewrite_relative(self, text: str, src: str) -> str:
        """Resolve relative and root-relative references against the file's own URL.

        The browser sees `news.css?v=3` in the HTML and requests https://host/news.css?v=3;
        the absolute-URL pass below never sees that string, so it has to be resolved here.
        """
        base = self.source_of.get(src)
        if not base or len(text) > 6_000_000:
            return text
        cache: dict[str, str | None] = {}
        is_code = src.lower().endswith((".js", ".mjs", ".json"))

        def sub(m: re.Match) -> str:
            tok = m.group("u")
            if tok in cache:
                hit = cache[tok]
            else:
                hit = None
                if not tok.startswith(("#", "data:", "javascript:", "mailto:", "tel:")) and ("/" in tok or "." in tok):
                    try:
                        full = urljoin(base, tok.replace("&amp;", "&")).split("#")[0]
                    except ValueError:
                        full = ""
                    mapped = self.urls.get(full)
                    if mapped is None and full.endswith("/") is False:
                        mapped = self.urls.get(full + "/")
                    if is_code and (full.endswith("/") or "." not in full.rsplit("/", 1)[-1]):
                        mapped = None       # in code, "/." or "../" is a string, not a link to the start page
                    if mapped is not None:
                        hit = relative(src, mapped)
                cache[tok] = hit
            return m.group("q") + hit if hit else m.group(0)
        return self.TOKEN.sub(sub, text)

    FLIGHT = re.compile(r"<script[^>]*>(?:(?!</script>).)*?__next_f(?:(?!</script>).)*</script>", re.S)

    def rewrite(self, text: str, src: str) -> str:
        # Next.js streams its React data as length-prefixed rows inside inline scripts.
        # Changing a URL inside one changes its length and the page dies with
        # "Connection closed", so those blocks are left exactly as the server sent them.
        keep: list[str] = []

        def stash(m: re.Match) -> str:
            keep.append(m.group(0))
            return f"\x00CPKEEP{len(keep) - 1}\x00"
        if src.endswith(".html") and "__next_f" in text:
            text = self.FLIGHT.sub(stash, text)
        text = self._rewrite(text, src)
        for i, block in enumerate(keep):
            text = text.replace(f"\x00CPKEEP{i}\x00", block)
        return text

    def _rewrite(self, text: str, src: str) -> str:
        text = self.rewrite_relative(text, src)
        origin = urlparse(self.origin)
        for url in sorted(self.urls, key=len, reverse=True):
            local = relative(src, self.urls[url]).replace("\\", "\\\\")
            bare = url.split("://", 1)[-1]
            for form in (url, "//" + bare):
                text = re.sub(re.escape(form) + BOUNDARY, local, text)
            u = urlparse(url)
            if u.netloc == origin.netloc:
                pth = u.path + (f"?{u.query}" if u.query else "")
                if len(pth) > 4:
                    text = re.sub(rf'(["\'(]){re.escape(pth)}(["\')])', rf"\g<1>{local}\g<2>", text)
        start = self.urls.get(self.origin) or self.urls.get(self.origin.rstrip("/") + "/")
        if start:
            to_start = relative(src, start).replace("\\", "\\\\")
            for bare in (self.origin.rstrip("/"), "//" + self.origin.split("://", 1)[-1].rstrip("/")):
                text = re.sub(re.escape(bare) + BOUNDARY, to_start, text)
        return text

    def write(self) -> dict[str, Any]:
        root = self.folder.resolve()
        for p, body in self.files.items():
            dst = self.folder / p
            if not str(dst.resolve()).startswith(str(root)):
                continue                                  # belt and braces: never write outside the mirror
            dst.parent.mkdir(parents=True, exist_ok=True)
            if Path(p).suffix.lower() in TEXT_EXT:
                text = self.rewrite(body.decode("utf-8", errors="replace"), p)
                if p.endswith(".html") and not re.search(r"<meta[^>]+charset", text[:4096], re.I):
                    text = re.sub(r"(<head[^>]*>)", r'\1<meta charset="utf-8">', text, count=1, flags=re.I) \
                        if re.search(r"<head", text, re.I) else '<meta charset="utf-8">' + text
                dst.write_text(text, encoding="utf-8")
            else:
                dst.write_bytes(body)
        return {"files": len(self.files), "bytes": sum(len(b) for b in self.files.values()),
                "skipped": self.skipped}


HARVEST_JS = r"""
() => {
  const out = new Set();
  const add = u => { if (!u) return; try { out.add(new URL(u, document.baseURI).href.split('#')[0]); } catch (e) {} };
  const srcset = v => (v || '').split(',').forEach(p => add(p.trim().split(/\s+/)[0]));
  document.querySelectorAll('img').forEach(i => { add(i.currentSrc); add(i.src); srcset(i.srcset); });
  document.querySelectorAll('source').forEach(i => { srcset(i.srcset); add(i.src); });
  document.querySelectorAll('video').forEach(v => { add(v.currentSrc); add(v.src); add(v.poster); });
  document.querySelectorAll('link[href]').forEach(l => { if (/icon|preload|manifest|stylesheet/.test(l.rel)) add(l.href); });
  document.querySelectorAll('*').forEach(el => {
    const bg = getComputedStyle(el).backgroundImage;
    if (bg && bg !== 'none') for (const m of bg.matchAll(/url\(["']?([^"')]+)["']?\)/g)) add(m[1]);
  });
  return Array.from(out).filter(u => u.startsWith('http'));
}
"""


async def capture_async(url: str, folder: Path, wait_ms: int = 6000, say=lambda s: None,
                        heal_rounds: int = 3, user_agent: str | None = None) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    m = Mirror(url, folder)
    pending: list[asyncio.Task] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=LAUNCH_ARGS)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                      user_agent=user_agent or normal_user_agent(browser.version))

        async def grab(resp) -> None:
            try:
                if resp.status >= 400 or resp.request.method != "GET":
                    return
                ct = (resp.headers.get("content-type") or "").lower() or "application/octet-stream"
                m.add(resp.url, ct, await resp.body())
            except Exception:
                pass

        page.on("response", lambda r: pending.append(asyncio.create_task(grab(r))))
        say(f"opening {url}")
        first = await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        main_status = first.status if first else 0
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(wait_ms)
        say("scrolling through the page")
        await asyncio.wait_for(page.evaluate("""async () => {
            const step = window.innerHeight * 0.7;
            let n = 0;
            for (let y = 0; y < document.body.scrollHeight && n < 80; y += step, n++) {
              window.scrollTo(0, y); await new Promise(r => setTimeout(r, 160));
            }
            window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 1000));
            window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 1000));
        }"""), timeout=60)
        await page.wait_for_timeout(2500)
        # Second pass: wake every lazy image, then fetch anything the DOM references that the
        # network listener has not seen (srcset candidates, posters, CSS backgrounds).
        say("harvesting everything the page references")
        try:
            await page.evaluate("document.querySelectorAll('img[loading=lazy]').forEach(i => { i.loading = 'eager'; })")
            await page.evaluate("""async () => {
                const imgs = Array.from(document.images);
                for (const i of imgs) { i.scrollIntoView({block: 'center'}); await new Promise(r => setTimeout(r, 40)); }
                window.scrollTo(0, 0);
            }""")
            await page.wait_for_timeout(2000)
            await asyncio.gather(*pending, return_exceptions=True)
            for u in await page.evaluate(HARVEST_JS):
                if u.split("#")[0] in m.urls:
                    continue
                try:
                    r = await page.context.request.get(u, timeout=30000)
                    if r.status < 400:
                        m.add(u, (r.headers.get("content-type") or "application/octet-stream").lower(), await r.body())
                except Exception:
                    pass
        except Exception:
            pass
        final_url = page.url
        try:
            live_text = int(await page.evaluate("document.body ? document.body.innerText.length : 0"))
        except Exception:
            live_text = 0
        await asyncio.gather(*pending, return_exceptions=True)
        await browser.close()

    if main_status >= 400:
        raise RuntimeError(
            f"{url} answered HTTP {main_status} (a block or an error page), so there is nothing to mirror. "
            "Try again later, use --chrome / --headed, or open it once in your own browser (cookies: --header).")
    if final_url.rstrip("/") != url.rstrip("/"):
        if urlparse(final_url).netloc == urlparse(url).netloc:
            m.origin = final_url       # redirect on the same host: treat the final URL as the page
        else:
            m.rebase(final_url)        # redirect to another host (apex -> www): that host is the site
    folder.mkdir(parents=True, exist_ok=True)
    say("fetching video/3D files in full")
    await asyncio.to_thread(m.fetch_full_media_blocking)
    info = m.write()
    if heal_rounds:
        info["healed"] = await heal(m, folder, heal_rounds, say)
        info = {**info, "files": len(m.files), "bytes": sum(len(b) for b in m.files.values())}
    start = local_path(m.origin, m.origin, "text/html")
    if not (folder / start).exists():
        htmls = sorted(p for p in m.files if p.endswith(".html"))
        start = htmls[0] if htmls else ""
    info["start"] = start
    info["live_text_chars"] = live_text
    info["source"] = url
    (folder / "_sources.json").write_text(json.dumps(
        {"source": url, "files": {p: u for u, p in sorted(m.urls.items())}}, indent=2), encoding="utf-8")
    return info


async def heal(m: Mirror, folder: Path, rounds: int = 3, say=lambda s: None) -> int:
    """Open the mirror, find what it asks for that it does not have, fetch that from the original.

    JavaScript often builds URLs at run time (`'models/' + name + '.glb'`), so the page never
    asked for them while we recorded it, or asked in a way we could not rewrite. The mirror
    shows exactly which ones are missing: they 404 on localhost. Each round fills the holes.
    """
    from playwright.async_api import async_playwright

    from .serve import serve

    added_total = 0
    for rnd in range(1, rounds + 1):
        srv, port = serve(folder, spa=False)
        missing: set[str] = set()
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(args=LAUNCH_ARGS)
                page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                              user_agent=normal_user_agent(browser.version))
                page.on("response", lambda r: missing.add(r.url) if r.status == 404
                        and r.url.startswith(f"http://127.0.0.1:{port}/") else None)
                try:
                    start = local_path(m.origin, m.origin, "text/html")
                    await page.goto(f"http://127.0.0.1:{port}/{start}", wait_until="domcontentloaded", timeout=60000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(3000)
                    await asyncio.wait_for(page.evaluate("""async () => {
                        let n = 0;
                        for (let y = 0; y < document.body.scrollHeight && n < 60; y += window.innerHeight * 0.7, n++) {
                          window.scrollTo(0, y); await new Promise(r => setTimeout(r, 140));
                        }
                        window.scrollTo(0, 0);
                    }"""), timeout=45)
                    await page.wait_for_timeout(2500)
                except Exception:
                    pass
                await browser.close()
        finally:
            srv.shutdown()
        origin = urlparse(m.origin)
        added = 0
        for u in sorted(missing):
            path = urlparse(u).path
            real = f"{origin.scheme}://{origin.netloc}{path}"
            if real in m.urls:
                continue
            def download(url=real):
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 cloneproof/0.1"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.read(), (r.headers.get("content-type") or "").lower() or "application/octet-stream"
            try:
                body, ctype = await asyncio.to_thread(download)
            except Exception:
                continue
            if "text/html" in ctype and not path.endswith((".html", "/")):
                continue            # a soft-404 page, not the file
            m.add(real, ctype if "octet" not in ctype or not path.endswith(MEDIA_EXT) else "model/gltf", body)
            added += 1
        say(f"heal round {rnd}: {len(missing)} missing, {added} fetched")
        added_total += added
        if added == 0:
            break
        m.write()
    return added_total


async def verify_mirror(folder: Path, start: str, live_text: int) -> dict[str, Any]:
    """Open the finished mirror and check that it really shows the page: page errors, and how much
    visible text it has compared with the live page. A mirror that opens blank is worse than none."""
    from playwright.async_api import async_playwright

    from .serve import serve

    srv, port = serve(folder)
    errors: list[str] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=LAUNCH_ARGS)
            page = await browser.new_page(viewport={"width": 1440, "height": 900},
                                          user_agent=normal_user_agent(browser.version))
            page.on("pageerror", lambda e: errors.append(str(e)[:120]))
            try:
                await page.goto(f"http://127.0.0.1:{port}/{start}", wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                await page.wait_for_timeout(2500)
                text = int(await page.evaluate("document.body ? document.body.innerText.length : 0"))
            except Exception as e:
                text = 0
                errors.append(str(e)[:120])
            await browser.close()
    finally:
        srv.shutdown()
    ok = text >= max(40, 0.5 * live_text) if live_text else text > 0
    if live_text and live_text < 30:
        ok = False           # a live page with almost no text is probably a block or challenge page
    return {"ok": ok, "mirror_text_chars": text, "live_text_chars": live_text, "page_errors": errors[:3]}


def capture(url: str, folder: str | Path, timeout_s: int = 420, attempts: int = 2, **kw) -> dict[str, Any]:
    """Mirror `url`. After writing, open the mirror and check it shows the page; if it does not
    (a transient error page was saved, a blocked request, ...), try again once."""
    async def go():
        return await asyncio.wait_for(capture_async(url, Path(folder), **kw), timeout=timeout_s)

    info: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        try:
            info = asyncio.run(go())
        except asyncio.TimeoutError:
            raise RuntimeError(f"capture of {url} did not finish within {timeout_s}s") from None
        info["verify"] = asyncio.run(verify_mirror(Path(folder), info["start"], info.get("live_text_chars", 0)))
        info["attempts"] = attempt
        if info["verify"]["ok"]:
            break
        kw.get("say", lambda s: None)(f"the mirror looks wrong ({info['verify']}); trying again")
    return info
