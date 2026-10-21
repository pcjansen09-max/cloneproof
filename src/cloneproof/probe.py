"""Load a page in a real browser and record everything we can measure about it.

One probe = one page load at one viewport width. It produces:

  * screenshots at fixed absolute scroll positions (so reference and clone are always
    photographed at the same place),
  * a DOM snapshot: every meaningful element with its box and computed style,
  * console errors, failed requests and the list of fonts that really loaded.

Scrolling is done like a visitor does it (top to bottom, with pauses) before measuring,
because lazy images, scroll-triggered animations and smooth-scroll libraries only wake up
when somebody scrolls.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from .browser import normal_user_agent

VIEWPORTS = {"mobile": (390, 844), "tablet": (768, 1024), "desktop": (1440, 900)}
MAX_FRAMES = 24

# Runs in the page. Returns a list of element records in document order.
SNAPSHOT_JS = r"""
() => {
  const out = [];
  const sy = window.scrollY, sx = window.scrollX;
  const textTags = new Set(['H1','H2','H3','H4','H5','H6','P','A','BUTTON','LI','SPAN','LABEL','TD','TH','DT','DD','FIGCAPTION','BLOCKQUOTE','SUMMARY','INPUT','TEXTAREA','SELECT','STRONG','EM','B','I','SMALL','CODE','PRE']);
  const mediaTags = new Set(['IMG','VIDEO','CANVAS','SVG','IFRAME','PICTURE','AUDIO']);
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const pathOf = el => {
    const parts = [];
    let n = el;
    while (n && n.nodeType === 1 && parts.length < 4) {
      let p = n.tagName.toLowerCase();
      if (n.id) { p += '#' + n.id; parts.unshift(p); break; }
      const cls = (typeof n.className === 'string' ? n.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) p += '.' + cls.join('.');
      parts.unshift(p);
      n = n.parentElement;
    }
    return parts.join(' > ');
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let el = walker.currentNode, count = 0;
  while ((el = walker.nextNode()) && count < 2500) {
    const tag = el.tagName;
    if (['SCRIPT','STYLE','NOSCRIPT','LINK','META','TEMPLATE','HEAD'].includes(tag)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    let own = '';
    for (const c of el.childNodes) if (c.nodeType === 3) own += c.nodeValue;
    own = norm(own);
    const isMedia = mediaTags.has(tag.toUpperCase());
    const hasText = own.length > 0 && (textTags.has(tag) || el.children.length === 0 || true);
    if (!hasText && !isMedia) {
      const bg = cs.backgroundColor, bi = cs.backgroundImage;
      const visibleBox = (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') || (bi && bi !== 'none');
      if (!visibleBox || r.width * r.height < 400) continue;
    }
    const rec = {
      tag: tag.toLowerCase(),
      path: pathOf(el),
      text: own.slice(0, 120),
      x: Math.round((r.left + sx) * 10) / 10,
      y: Math.round((r.top + sy) * 10) / 10,
      w: Math.round(r.width * 10) / 10,
      h: Math.round(r.height * 10) / 10,
      media: isMedia,
      fixed: cs.position === 'fixed' || cs.position === 'sticky',
      s: {
        fontFamily: (cs.fontFamily || '').split(',')[0].replace(/["']/g, '').trim(),
        fontSize: cs.fontSize, fontWeight: cs.fontWeight, lineHeight: cs.lineHeight,
        letterSpacing: cs.letterSpacing, color: cs.color, background: cs.backgroundColor,
        borderRadius: cs.borderRadius, opacity: cs.opacity, textAlign: cs.textAlign,
        textTransform: cs.textTransform, display: cs.display,
        backgroundImage: cs.backgroundImage === 'none' ? '' : cs.backgroundImage.slice(0, 200),
        boxShadow: cs.boxShadow === 'none' ? '' : cs.boxShadow, borderTopWidth: cs.borderTopWidth, borderTopColor: cs.borderTopColor,
      },
    };
    rec.alt = norm(el.getAttribute('alt') || el.getAttribute('aria-label') || '').slice(0, 60);
    if (tag === 'IMG') rec.src = (el.currentSrc || el.src || '').split('?')[0].split('/').pop();
    if (tag === 'VIDEO') rec.src = ((el.currentSrc || el.src || '').split('?')[0].split('/').pop());
    if (tag === 'A') rec.href = el.getAttribute('href') || '';
    if (cs.backgroundImage && cs.backgroundImage !== 'none') rec.bgimg = cs.backgroundImage.slice(0, 80);
    out.push(rec);
    count++;
  }
  return out;
}
"""

SCROLL_THROUGH_JS = """
async (pause) => {
  const step = Math.max(200, window.innerHeight * 0.7);
  const total = () => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
  let n = 0;
  for (let y = 0; y < total() && n < 80; y += step, n++) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, pause));
  }
  window.scrollTo(0, total());
  await new Promise(r => setTimeout(r, pause * 4));
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, pause * 4));
}
"""

FREEZE_MEDIA_JS = """
() => {
  document.querySelectorAll('video').forEach(v => { try { v.pause(); } catch (e) {} });
  document.querySelectorAll('video, iframe').forEach(v => { v.dataset.cpHidden = v.style.visibility; v.style.visibility = 'hidden'; });
  const st = document.getElementById('__cp_style') || document.createElement('style');
  st.id = '__cp_style';
  st.textContent = '*{caret-color:transparent !important} ::-webkit-scrollbar{display:none !important} html{scrollbar-width:none !important}';
  document.head.appendChild(st);
}
"""

UNFREEZE_MEDIA_JS = """
() => {
  document.querySelectorAll('video, iframe').forEach(v => { v.style.visibility = v.dataset.cpHidden || ''; });
}
"""


@dataclass
class Probe:
    url: str
    viewport: str
    width: int
    height: int
    page_height: int = 0
    positions: list[int] = field(default_factory=list)
    frames: list[Image.Image] = field(default_factory=list)
    elements: list[dict[str, Any]] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    title: str = ""
    requests: list[str] = field(default_factory=list)


def plan_positions(page_height: int, view_height: int, max_frames: int = MAX_FRAMES) -> list[int]:
    """Absolute scroll offsets that tile the page, evenly thinned if the page is very tall."""
    max_scroll = max(page_height - view_height, 0)
    if max_scroll == 0 or max_frames < 2:
        return [0]
    step = max(int(view_height * 0.9), 1)
    pos = list(range(0, max_scroll, step)) + [max_scroll]
    if len(pos) > max_frames:
        pos = [round(i * max_scroll / (max_frames - 1)) for i in range(max_frames)]
    return sorted(set(int(p) for p in pos))


async def _settle(page, wait_ms: int) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    await page.wait_for_timeout(wait_ms)
    try:
        await page.evaluate("document.fonts && document.fonts.ready")
    except Exception:
        pass


async def _probe_page(browser, url: str, viewport: str, *, wait_ms: int = 2500,
                     settle_ms: int = 900, positions: list[int] | None = None,
                     max_frames: int = MAX_FRAMES, headers: dict | None = None,
                     user_agent: str | None = None) -> Probe:
    """Load `url` at one viewport and measure it."""
    width, height = VIEWPORTS[viewport]
    ctx = await browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=1,
        is_mobile=(viewport == "mobile"),
        has_touch=(viewport == "mobile"),
        extra_http_headers=headers or {},
        user_agent=user_agent or normal_user_agent(browser.version),
        locale="en-US",
        timezone_id="Europe/Amsterdam",
    )
    page = await ctx.new_page()
    result = Probe(url=url, viewport=viewport, width=width, height=height)
    page.on("console", lambda m: result.console_errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("requestfailed", lambda r: result.failed_requests.append(
        f"{r.url[:160]} ({(r.failure or '')[:40]})") if "ABORTED" not in str(r.failure) else None)
    page.on("response", lambda r: result.failed_requests.append(f"{r.url[:160]} (HTTP {r.status})")
            if r.status >= 400 else None)
    page.on("request", lambda r: result.requests.append(r.url.split("?")[0].split("#")[0]))
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await _settle(page, wait_ms)
        await asyncio.wait_for(page.evaluate(SCROLL_THROUGH_JS, 140), timeout=60)
        await _settle(page, 600)
        result.title = await page.title()
        result.page_height = int(await page.evaluate(
            "Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)"))
        result.positions = positions if positions is not None else plan_positions(
            result.page_height, height, max_frames)
        result.fonts = sorted(set(await page.evaluate(
            "Array.from(document.fonts || []).filter(f => f.status === 'loaded').map(f => f.family.replace(/[\"']/g,'') + ' ' + f.weight)")))
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(settle_ms)
        result.elements = await page.evaluate(SNAPSHOT_JS)
        for y in result.positions:
            await page.evaluate("y => window.scrollTo(0, y)", y)
            await page.wait_for_timeout(settle_ms)
            await page.evaluate(FREEZE_MEDIA_JS)
            await page.wait_for_timeout(120)
            png = None
            for attempt in range(4):
                try:
                    png = await page.screenshot(type="png", timeout=45000)
                    break
                except Exception:
                    # heavy WebGL pages sometimes refuse a capture mid-frame; wait and retry
                    await page.wait_for_timeout(1200 * (attempt + 1))
                    try:
                        await page.evaluate("y => window.scrollTo(0, y)", y)
                    except Exception:
                        pass
            if png is None:
                png = await page.screenshot(type="jpeg", quality=92, timeout=60000)
            result.frames.append(Image.open(io.BytesIO(png)).convert("RGB"))
            await page.evaluate(UNFREEZE_MEDIA_JS)
    finally:
        await ctx.close()
    return result


async def probe_page(browser, url: str, viewport: str, *, timeout_s: int = 300, **kw) -> Probe:
    """`_probe_page` with a hard ceiling, so one heavy page cannot hang a whole run."""
    try:
        return await asyncio.wait_for(_probe_page(browser, url, viewport, **kw), timeout=timeout_s)
    except asyncio.TimeoutError:
        raise RuntimeError(f"{url} ({viewport}) did not finish within {timeout_s}s; "
                           "try --quick, a higher --settle, or --chrome") from None
