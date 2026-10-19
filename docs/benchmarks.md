# Stress test on real sites

How well does cloneproof hold up on real, messy websites? Method: mirror each live site with
`cloneproof capture`, then measure the mirror against the live site with `cloneproof compare`
(desktop + mobile, noise calibration on). A perfect mirror and a perfect measurement would give 100.
Whatever is lower is either a hole in the mirror or a weak spot in the measurement, and the issue list
says which. Run on 19 October 2026, headless Chromium 156, software rendering (no GPU), macOS.

| site | type | score | what the report pointed at |
|---|---|---|---|
| example.com | static | **100** | |
| news.ycombinator.com | static, table layout | **100** | |
| threejs.org | WebGL docs site | **99.8** | |
| linear.app | animated SaaS (Next.js) | **98.3** | |
| delta-design.nl (own site) | Next.js, WebGL hero (desktop) | **96.9** | scroll-reveal opacity, one font fallback |
| wordpress.org | WordPress | **96.4** | |
| en.wikipedia.org (article) | MediaWiki | **93.7** | |
| bedrijfsstack.nl (own site) | scroll-linked product story | 86.5 | sticky elements at a different scroll phase |
| tailwindcss.com | Next.js, big showcase | 85.0 | lazy images in a showcase grid |
| stripe.com | heavy marketing site | 83.1 | animated gradients, scroll-linked sections |
| framer.com | Framer site | 65.2 | URLs built in JavaScript at run time |
| bruno-simon.com | WebGL game | 64.7 (81 with `--wait 15000`) | 3D scene needs longer to load |
| resend.com | Next.js, sticky sections | 60.1 | page 186px shorter, shifts a scroll-pinned section |
| vercel.com | WebGL-heavy | n/a | capture timed out in software rendering |

Median of the 13 scored sites: **93.7**.

## What running this found (and fixed)

The first run scored Hacker News 41 and Wikipedia 19. Both were bugs in cloneproof, not in the sites:

1. Relative URLs with a query string (`news.css?v=3`) were never rewritten, so the mirror lost its styles.
2. Stylesheet links containing `&amp;` (Wikipedia, MediaWiki) were not matched.
3. Mirrored HTML had no charset header, so `–` turned into `â€“`.
4. A site that redirects `example.nl` to `www.example.nl` was saved under the wrong root.
5. Rewriting URLs inside Next.js streaming data (`self.__next_f.push`) broke its length-prefixed rows
   and killed hydration ("Connection closed"). Those blocks are now left untouched.
6. Lazy images that were never requested during the scroll are now harvested from `srcset`, `<picture>`,
   posters and CSS backgrounds.
7. Files that JavaScript builds URLs for at run time (3D models, wasm) are found by opening the mirror,
   collecting what 404s, and fetching exactly those from the original ("heal" pass).
8. Image filenames change in a mirror (`image-89bfc0.webp`), so images are now matched by alt text or
   size instead of file name.

## Honest limits

- This measures the mirror as much as it measures cloneproof. It is a stress test, not an accuracy claim.
- Sites with scroll-pinned sections and sites that need a GPU score lower; a different scroll phase shifts
  every frame below it.
- Numbers depend on timing (`--wait`) for heavy pages. Re-run before you trust a single value.

## The agent loop on a made-up site (Fika Roasters, `examples/fika`)

An AI (Claude Sonnet) rebuilt the page from screenshots only, then `cloneproof loop` measured it and handed the
differences back, round after round. Same start clone, same agent, same target:

| run | start | after 5 rounds | after 8 rounds | notes |
|---|---|---|---|---|
| first run, desktop + mobile only | 57.3 | 86.9 | 90.2 (6 rounds); 96.6 after 3 more | scores cover two widths |
| three widths, plain prompt | 58.4 | 78.2 | 79.8 (81.6 after the 9th measurement) | |
| three widths, prompt with size hints | 58.6 | 76.7 | not finished | |
| three widths, prompt with page map | 58.9 | 79.9 | 82.7 | |
| earlier clone, three widths, continued | 85.7 | 96.8 | 96.8 best, one round rolled back | |

What this says, honestly: the loop reliably lifts a clone by 20+ points and the extra prompt detail helps a little
(a few points, single runs, noisy). Going from the low 80s to 97 takes many more rounds or a smarter agent; it is not
automatic. One run, where the original sat next to the clone as a local folder, hit a perfect 100 after one round because
the agent copied the original's files. The loop now detects that and rolls it back.
