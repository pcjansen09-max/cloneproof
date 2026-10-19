# Fika Roasters demo

A fictional coffee roaster landing page used to demonstrate `cloneproof loop`. Everything here is made up.

- `original/`: the page we pretend to clone.
- `screenshots/`: what the AI saw (desktop and mobile frames). It saw nothing else.
- `clone/`: the AI's clone after the loop (best version, score 96.6; it started at 57.3).

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
