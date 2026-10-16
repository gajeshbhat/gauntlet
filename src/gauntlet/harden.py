"""Harden gate (Python): the mutation score from `mutmut results --all true` must reach `mutation.min_score`.

The gate only reads results; mutmut itself runs in the sandbox (`gauntlet run`), never on the host.
"""

from gauntlet.results import Mutation

CAUGHT = {"killed", "timeout", "segfault"}
IGNORED = {"skipped"}


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


def check(results: str) -> Mutation:
    caught, total, bad = score(results)
    return Mutation(100 * caught / total, bad, caught, total)
