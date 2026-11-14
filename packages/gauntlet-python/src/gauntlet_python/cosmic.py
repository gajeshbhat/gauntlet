"""Cosmic Ray's report: the one-line-per-mutant text the sandbox makes from `cosmic-ray dump`.

Same shape as mutmut's, so the gate does not care which tool ran: `<file>:<line> <operator>: <status>`, where the
status is the test outcome, else the worker outcome, else `pending`.
"""

from pathlib import Path

from gauntlet.plugin import MutationTool, Where


def locate(names: list[str], root: Path) -> dict[str, Where]:  # noqa: ARG001
    """The name already says where: `src/a.py:4 core/Op_Eq_NotEq`."""
    found: dict[str, Where] = {}
    for name in names:
        path, _, line = name.partition(" ")[0].rpartition(":")
        if path and line.isdigit():
            found[name] = (path, int(line), int(line))
    return found


TOOL = MutationTool(
    artifact="mutmut-results.txt",  # the same name as mutmut's: it predates the second tool
    how='set [mutation] tool = "cosmic-ray" and run: gauntlet run',
    caught=frozenset({"killed", "incompetent"}),  # a mutant the tests time out on counts as killed, like mutmut
    ignored=frozenset({"no-test"}),  # no mutation was possible at that spot
    never_ran=frozenset({"abnormal", "exception", "pending"}),
    empty='no mutants found; does [mutation] tool = "cosmic-ray" see any source under src?',
    broken=(
        "cosmic-ray ran no mutant: its workers never produced a result. "
        "Run `cosmic-ray baseline` and `cosmic-ray exec` in the project to see why."
    ),
    locate=locate,
)
