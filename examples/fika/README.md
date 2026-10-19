# Fika Roasters demo

A fictional coffee roaster landing page used to demonstrate `cloneproof loop`. Everything here is made up.

- `original/`: the page we pretend to clone.
- `screenshots/`: what the AI saw (desktop and mobile frames). It saw nothing else.
- `clone/`: the AI's clone after three consecutive loop runs (best version: 96.8 on desktop, tablet and mobile; the first run started at 57.3 on desktop + mobile).

Reproduce the measurement:

```bash
cloneproof compare examples/fika/original examples/fika/clone --open
```

Reproduce the loop (needs the `claude` CLI; any agent that reads a prompt on stdin works):

```bash
cloneproof loop examples/fika/original examples/fika/clone \
  --agent "claude -p --permission-mode acceptEdits --allowedTools Read,Edit,Write --add-dir $PWD/.cloneproof" \
  --cwd examples/fika/clone --rounds 5 --target 97
```

A from-scratch run over all three widths reaches about 82 in eight rounds (three measured runs: 81.6, ~77 and 82.7 from a start of 58);
getting past 90 takes more rounds. See docs/benchmarks.md.
