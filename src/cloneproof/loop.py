"""Autonomous feedback loop: measure, hand the differences to an agent, measure again."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

from .compare import compare
from .prompt import build_prompt
from .report import write_all


def run_loop(reference: str, clone: str, *, agent: str, target: float, rounds: int, out: Path,
             cwd: Path, compare_kw: dict, say=lambda s: print(s, file=sys.stderr),
             hint: str = "", agent_timeout: int = 1800) -> dict:
    """Each round: compare -> write prompt -> run `agent` with the prompt on stdin.

    Stops when the target is reached, when a round fails to improve twice in a row, or after
    `rounds` rounds. The final measurement is always taken after the last agent run.
    """
    history: list[float] = []
    stalled = 0
    result = None
    for n in range(1, rounds + 2):
        rdir = out / f"round-{n:02d}"
        result = compare(reference, clone, rdir, say=lambda s: None, **compare_kw)
        prompt = build_prompt(result, target=target, clone_hint=hint, round_no=n)
        write_all(result, prompt)
        (out / "latest").unlink(missing_ok=True) if (out / "latest").is_symlink() else None
        try:
            (out / "latest").symlink_to(rdir.name)
        except OSError:
            pass
        history.append(round(result.score, 1))
        say(f"round {n}: score {result.score:.1f} ({', '.join(f'{k} {v.score:.0f}' for k, v in result.viewports.items())})")
        if result.score >= target:
            say(f"target {target:g} reached")
            break
        if n > rounds:
            say("round limit reached")
            break
        if len(history) >= 2 and history[-1] <= history[-2] + 0.2:
            stalled += 1
        else:
            stalled = 0
        if stalled >= 2:
            say("no improvement in two rounds, stopping")
            break
        say(f"round {n}: handing {len(result.issues())} differences to the agent")
        t0 = time.time()
        try:
            subprocess.run(shlex.split(agent), input=prompt, text=True, cwd=str(cwd), timeout=agent_timeout)
        except subprocess.TimeoutExpired:
            say("agent timed out")
        except FileNotFoundError:
            say(f"agent command not found: {agent.split()[0]}")
            break
        say(f"round {n}: agent finished in {time.time() - t0:.0f}s")
    summary = {"history": history, "final": history[-1] if history else None, "target": target,
               "reached": bool(result and result.score >= target)}
    (out / "loop.json").write_text(json.dumps(summary, indent=2))
    return summary
