# Showdown: who saves a web page best?

Four tools save the same page for offline use. Then `cloneproof compare` measures the saved copy against the live
site on desktop and mobile (pixels with noise removed, layout, style, text, assets, scroll motion). 100 means a visitor
cannot tell them apart. Seven real sites, 20 October 2026, headless Chromium 156 on macOS, one machine, nothing else running.

| site | cloneproof capture | SingleFile | HTTrack | wget |
|---|---|---|---|---|
| example | 100.0 | 100.0 | 100.0 | 100.0 |
| hackernews | 100.0 | 100.0 | 55.4 | 100.0 |
| wikipedia | 99.1 | 97.7 | failed | 97.7 |
| wordpress | 99.9 | 93.4 | failed | 56.7 |
| linear | 99.7 | 65.1 | 39.6 | 81.7 |
| tailwind | 87.1 | 86.2 | 30.7 | 87.8 |
| threejs | 99.8 | 100.0 | 100.0 | 100.0 |
| **mean (failed = 0)** | **97.9** | **91.8** | **46.5** | **89.1** |
| **median of scored** | **99.8** | **97.7** | **55.4** | **97.7** |

Tools and settings: `cloneproof capture` (this repo, default); SingleFile CLI (single-file-cli, 4 s wait); HTTrack 3.50.5
(`-r2 -n`, 300 s limit); GNU wget 1.25 (`-E -H -k -K -p`, the "save this page with its files" recipe).
Reproduce: `python scripts/showdown.py` (needs `brew install httrack`, `npm i single-file-cli`).

## What it shows
- A real browser that scrolls the page and then checks the result beats the older recipes on pages that rely on JavaScript
  (Linear, WordPress). On plain pages (example.com, Hacker News, three.js) everything that works scores near 100.
- HTTrack has no JavaScript engine and failed or timed out on the heavier pages. SingleFile saves one static file
  (default settings), which does not keep scroll-driven behaviour. wget keeps the HTML but misses assets that scripts request.
- Tailwind's site (a large lazy-loaded showcase) is hard for every tool; cloneproof is level with the rest there.

## Read this with care
- **The judge is also a contestant.** cloneproof wrote the measurement and the capture. We tried to be fair (same settings,
  same page, one run each, no cherry-picking, failed runs counted as failures), but you should not take our word for it:
  the script is in this repo, run it yourself.
- One run per cell. Live sites change between runs (the first Hacker News run scored 87 because the front page had changed
  between capture and measurement; Linear scored 10.8 once when a mirror was saved while the site returned an error page,
  which is why `capture` now verifies the mirror and retries). Both cells above are the clean re-runs.
- The competing tools are built for other jobs (archiving, a single portable file). We measure what we care about, which is
  "does it look and behave like the original".
- Seven sites is a small sample. Pages behind a login, GPU-heavy sites and very long pages are not covered.
