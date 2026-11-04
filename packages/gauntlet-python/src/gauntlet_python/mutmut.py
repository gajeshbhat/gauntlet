"""Harden gate (Python): the mutation score from `mutmut results --all true` must reach `mutation.min_score`.

The gate only reads results; mutmut itself runs in the sandbox (`gauntlet run`), never on the host.
"""

from gauntlet.errors import GauntletError
from gauntlet.results import Mutation

CAUGHT = {"killed", "timeout", "segfault"}
IGNORED = {"skipped"}
NOT_RUN = (
    "mutmut checked no mutant: its tests never ran (a failing test or a layout it cannot handle makes it "
    "stop before the first mutant). Run `mutmut run` in the project to see why."
)


def _never_ran(caught: int, unmet: list[str]) -> bool:
    return caught == 0 and all(b.endswith(": not checked") for b in unmet)


def check(results: str) -> Mutation:
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
        raise GauntletError("no mutants found; is [tool.mutmut] configured in the target repo?")
    if _never_ran(caught, bad):
        raise GauntletError(NOT_RUN)
    return Mutation(100 * caught / total, bad, caught, total)
