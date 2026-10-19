"""Autonomous feedback loop: measure, hand the differences to an agent, measure again."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .compare import compare
from .prompt import build_prompt
from .report import write_all


SKIP = shutil.ignore_patterns("node_modules", ".git", ".next", "dist", "build", ".cloneproof", "__pycache__", ".venv")


def snapshot(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=SKIP)


def restore(snap: Path, dst: Path) -> None:
    """Put the project back exactly as the snapshot was (files the agent added are removed)."""
    for item in list(dst.iterdir()):
        if item.name in {"node_modules", ".git", ".next", "dist", "build", ".cloneproof", ".venv", "__pycache__"}:
            continue
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    for item in snap.iterdir():
        if item.is_dir():
            shutil.copytree(item, dst / item.name)
        else:
            shutil.copy2(item, dst / item.name)


def run_loop(reference: str, clone: str, *, agent: str, target: float, rounds: int, out: Path,
             cwd: Path, compare_kw: dict, say=lambda s: print(s, file=sys.stderr),
             hint: str = "", agent_timeout: int = 1800, ref_arg: str = "", clone_arg: str = "") -> dict:
    """Each round: compare -> write prompt -> run `agent` with the prompt on stdin.

    Stops when the target is reached, when a round fails to improve twice in a row, or after
    `rounds` rounds. The final measurement is always taken after the last agent run.
    """
    history: list[float] = []
    stalled = 0
    result = None
    best_score, best_round, best_prompt = -1.0, 0, ""
    for n in range(1, rounds + 2):
        rdir = out / f"round-{n:02d}"
        result = compare(reference, clone, rdir, say=lambda s: None, **compare_kw)
        prompt = build_prompt(result, target=target, clone_hint=hint, round_no=n, ref_arg=ref_arg, clone_arg=clone_arg)
        write_all(result, prompt)
        link = out / "latest"
        try:
            if link.is_symlink():
                link.unlink()
            link.symlink_to(rdir.name)
        except OSError:
            pass
        history.append(round(result.score, 1))
        say(f"round {n}: score {result.score:.1f} ({', '.join(f'{k} {v.score:.0f}' for k, v in result.viewports.items())})")
        improved = result.score > best_score + 0.2
        if result.score > best_score:
            best_score, best_round, best_prompt = result.score, n, prompt
            snapshot(cwd, out / "best")
        if result.score >= target:
            say(f"target {target:g} reached")
            break
        if n > rounds:
            say("round limit reached")
            break
        stalled = 0 if improved else stalled + 1
        if stalled >= 2:
            say("no improvement in two rounds, stopping")
            break
        if result.score < best_score - 0.2:
            say(f"round {n}: score fell from {best_score:.1f} to {result.score:.1f}; restoring the best version (round {best_round})")
            restore(out / "best", cwd)
            prompt = (f"NOTE: your changes in the previous round LOWERED the score to {result.score:.1f}, so the project "
                      f"was restored to the best version so far (round {best_round}, {best_score:.1f}). The list below belongs "
                      "to that version. Make smaller, safer changes; do not repeat the last attempt.\n\n") + best_prompt
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
    summary = {"history": history, "best": round(best_score, 1), "best_round": best_round, "target": target,
               "reached": best_score >= target}
    if best_round and (out / "best").exists() and result is not None and result.score < best_score:
        restore(out / "best", cwd)
    (out / "loop.json").write_text(json.dumps(summary, indent=2))
    return summary
