"""Browser setup shared by capture, probe and the checks.

Playwright's Chromium announces itself as "HeadlessChrome". Many sites (Cloudflare and friends) answer that with
HTTP 403 and an empty challenge page, so a tool that opens them headless saves nothing. A browser that presents
itself like an ordinary Chrome gets the page a visitor gets. This is not a way around a login or a CAPTCHA: when
a site really asks a human to prove something, use --chrome or --headed, or do it once in your own browser.
"""

from __future__ import annotations

import sys


def normal_user_agent(browser_version: str) -> str:
    """The user agent an ordinary Chrome of the same version sends (no "Headless")."""
    major = (browser_version or "130").split(".")[0]
    if sys.platform == "darwin":
        plat = "Macintosh; Intel Mac OS X 10_15_7"
    elif sys.platform.startswith("win"):
        plat = "Windows NT 10.0; Win64; x64"
    else:
        plat = "X11; Linux x86_64"
    return f"Mozilla/5.0 ({plat}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"


LAUNCH_ARGS = ["--enable-unsafe-swiftshader", "--disable-blink-features=AutomationControlled"]


async def launch(pw, *, headed: bool = False, channel: str | None = None, cdp: str | None = None,
                 extra_args: list[str] | None = None):
    """Start Chromium, or attach to a Chrome that is already running (`--remote-debugging-port`), with its own
    cookies and sessions. Attaching is the honest way through a bot wall: a human passed the check, we reuse it."""
    if cdp:
        browser = await pw.chromium.connect_over_cdp(cdp)
        browser._cp_cdp = True
        return browser
    opts: dict = {"args": [*(extra_args or []), *LAUNCH_ARGS], "headless": not headed}
    if channel:
        opts["channel"] = channel
    browser = await pw.chromium.launch(**opts)
    browser._cp_cdp = False
    return browser


async def new_page(browser, viewport: dict, user_agent: str | None = None, **ctx_kw):
    """A page with a viewport. In an attached Chrome it lives in the default context (cookies kept) and keeps that
    browser's own user agent; in our own Chromium it gets a fresh context with an ordinary Chrome user agent."""
    if getattr(browser, "_cp_cdp", False):
        page = await browser.contexts[0].new_page()
        await page.set_viewport_size(viewport)
        return page, None
    ctx = await browser.new_context(viewport=viewport, user_agent=user_agent or normal_user_agent(browser.version), **ctx_kw)
    return await ctx.new_page(), ctx
