# How cloneproof measures

A clone is "1:1" when a visitor cannot tell the two apart. That is a measurement, not an opinion,
and cloneproof measures it five ways at once, on three screen sizes.

## 1. The probe

For each viewport (desktop 1440, tablet 768, mobile 390) and each site, a real Chromium:

1. loads the page and waits for the preloader (`--wait`),
2. scrolls through the whole page like a visitor, so lazy images, scroll-triggered animations and
   smooth-scroll libraries wake up,
3. snapshots the DOM: every visible element with its box (document coordinates) and computed style
   (font, size, weight, colour, spacing, radius, background, shadow, border, opacity),
4. photographs the page at fixed **absolute** scroll offsets (decided by the original, reused for the clone),
   with videos and iframes hidden for the shot (their frame depends on network timing).

## 2. Noise calibration

No site looks identical to itself twice: carousels, clocks, GIFs, anti-aliasing. So the original is
probed **twice**. Every pixel that already differs between those two runs (grown by 4px) is masked out and
never counted against the clone. A perfect copy of a restless page still scores ~100.

## 3. Pixels, shift-tolerant

Per scroll frame the clone is compared to the original with a per-channel tolerance. Before comparing,
each 48px band of the clone is slid up or down (up to 240px, preferring the shift of the band above) to where it best matches. One heading that
is 10px taller would otherwise make everything below it "wrong"; the shift itself is reported as a
layout issue. The pixel score only counts pixels where either image shows something other than the frame's
dominant background colour, so a flat white page cannot score 99% for free.

## 4. Elements

The DOM snapshots are aligned (sequence match on tag + text/src, then fuzzy text for edited strings).
This finds, with a CSS selector and numbers:

- elements that are **missing** or **extra**,
- elements that are **moved** (a shift inherited from an element above is not blamed again),
- elements that are **resized**,
- **style** differences (`font-size: original 64px, clone 56px`),
- **text** differences.

## 5. Behaviour

- **Motion fingerprint**: how much the picture changes between consecutive scroll positions. A hero that
  animates in the original and sits still in the clone shows up as a motion issue at that scroll step.
- **Assets**: fonts that load in the original but not in the clone, failed requests, console errors that only
  the clone has.

## The score

Per viewport: visual 50%, layout 20%, style 12%, content 8%, assets 5%, motion 5%.
Across viewports: desktop 45%, mobile 35%, tablet 20%.

| score | meaning |
|---|---|
| 97+ | indistinguishable |
| 92-97 | very close |
| 80-92 | close, visible differences |
| 60-80 | recognisable, clearly different |
| < 60 | far off |

## The prompt

`cloneproof compare` writes `prompt.md`: the differences sorted by how visible they are, each with the
exact value to set (`set font-size: 64px on section.hero > h1`), the paths of the three images per
scroll position (original, clone, red diff), the exact command to measure again, and the rules
(fix source, never special-case the measurement). Paste it into any agent, or let `cloneproof loop` do it.

## Agents cheat, so the loop checks

In one test run an agent was given a local folder as "original", read the source files next to it and pasted them
into the clone: a perfect 100 after one round, and nothing cloned. The measurement was right (the pages really were
identical); the behaviour was wrong. `cloneproof loop` now hashes the clone's files against the original's folder, treats
a copy as a failed round, restores the best honest version and tells the agent why. The prompt also says it plainly.
When you can, give the loop the original as a URL instead of a path.

## What it cannot do (yet)

- WebGL/canvas content is compared as pixels only; if it is non-deterministic it is masked as noise.
- Pages behind a login or bot wall need `--headers` or a manual session.
- Hover, click and form states are not compared.
- Video content is not compared (timing-dependent); presence and size are.
