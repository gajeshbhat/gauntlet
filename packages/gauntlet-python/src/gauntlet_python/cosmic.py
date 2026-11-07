"""Harden gate (Python, Cosmic Ray): reads the one-line-per-mutant report the sandbox makes from `cosmic-ray dump`.

Same shape as mutmut.py, so the gate does not care which tool ran: `<mutant>: <status>`, where the status is the
test outcome, else the worker outcome, else `pending`.
"""

from gauntlet.errors import GauntletError
from gauntlet.results import Mutation

CAUGHT = {"killed", "incompetent"}  # Cosmic Ray counts a mutant its tests time out on as killed, like mutmut
IGNORED = {"no-test"}  # no mutation was possible at that spot
NEVER_RAN = {"abnormal", "exception", "pending"}
NOT_RUN = (
    "cosmic-ray ran no mutant: its workers never produced a result. "
    "Run `cosmic-ray baseline` and `cosmic-ray exec` in the project to see why."
)


def _never_ran(caught: int, unmet: list[str]) -> bool:
    return caught == 0 and all(b.rpartition(": ")[2] in NEVER_RAN for b in unmet)


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
        raise GauntletError('no mutants found; does [mutation] tool = "cosmic-ray" see any source under src?')
    if _never_ran(caught, bad):
        raise GauntletError(NOT_RUN)
    return Mutation(100 * caught / total, bad, caught, total)
