---
name: cloneproof
description: Measure how close a website clone is to the original and fix the differences in a loop until it is 1:1. Use whenever you rebuild, clone, migrate or restyle a website to match a reference site, or when asked to make a page "pixel perfect", "identical" or "1:1".
---

# cloneproof: measure first, then fix

Never judge a clone by looking at it. Measure it.

## The loop

1. Make sure the clone runs (dev server URL, or a folder of static files).
2. Measure:

   ```
   cloneproof compare <original-url> <clone-url-or-folder> --json --target 97
   ```

   - stdout is JSON: `score` (0-100), per viewport scores, and `issues` sorted by how visible they are.
   - exit code 0 = target reached, 1 = not yet.
   - `.cloneproof/latest/` holds `report.html`, `prompt.md`, and for every scroll position
     `NN-original.png`, `NN-clone.png`, `NN-diff.png` (red = different). Open the images when an
     issue is unclear.
3. Fix the biggest issues first, in the clone's source code. Typical fixes: set the exact
   computed style the issue names, move/resize a box, add the missing element, load the missing font,
   add the scroll animation.
4. Re-measure. Stop at the target, or when two rounds in a row do not improve the score.

Use `--quick` (desktop only, no noise calibration, ~3x faster) while iterating, and a full run
(desktop + tablet + mobile) before you say you are done.

## Rules

- Fix the source (HTML/CSS/JS/components). Do not paste screenshots in, do not hotlink the
  original's assets, do not detect the measurement and special-case it.
- Do not copy copyrighted content from a site you do not own or have permission to copy. Cloning
  your own site, a client's site, or a layout for learning is fine.
- Mobile counts for 35% of the score, tablet 20%. Check responsive rules, not only desktop.
- Large layout differences first (missing sections, wrong page height), then typography and colour, then single pixels.

## Categories in the score

visual 50% (pixels that differ, noise removed), layout 20% (box positions and sizes), style 12%
(font, size, weight, colour, spacing), content 8% (text), assets 5% (fonts/images that load),
motion 5% (does the page change while scrolling like the original does).

## Autonomous mode

```
cloneproof loop <original> <clone> --agent "claude -p --permission-mode acceptEdits" --target 97 --rounds 6
```

measures, hands the prompt to the agent, measures again.
