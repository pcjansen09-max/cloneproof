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
