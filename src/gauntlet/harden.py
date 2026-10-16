"""Harden gate: mutation testing via mutmut; the score must reach `mutation.min_score`."""

import subprocess
from collections.abc import Callable
from pathlib import Path

CAUGHT = {"killed", "timeout", "segfault"}
IGNORED = {"skipped"}

Run = Callable[..., "subprocess.CompletedProcess[str]"]


def score(results: str) -> tuple[int, int, list[str]]:
    caught, total = 0, 0
    bad: list[str] = []
    for line in results.splitlines():
        name, _, status = line.strip().partition(": ")
        if not status or status in IGNORED:
            continue
        total += 1
        if status in CAUGHT:
            caught += 1
        else:
            bad.append(f"{name}: {status}")
    if total == 0:
        raise ValueError("no mutants found; is [tool.mutmut] configured in the target repo?")
    return caught, total, bad


def check(root: Path, run: Run = subprocess.run) -> tuple[float, list[str]]:
    base = ["uv", "run", "--project", str(root), "mutmut"]
    run([*base, "run"], cwd=root, capture_output=True, text=True)
    done = run([*base, "results", "--all", "true"], cwd=root, capture_output=True, text=True)
    caught, total, bad = score(done.stdout)
    return 100 * caught / total, bad
