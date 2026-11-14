"""Harden gate: the share of planted bugs (mutants) the tests caught, among the mutants in scope.

A mutation tool's report is one `<mutant>: <status>` line per mutant, optionally followed by a tab and the change the
mutant made. The language plugin says what the statuses mean and where a mutant's code is.
"""

from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.plugin import MutationTool, Where
from gauntlet.results import Mutation
from gauntlet.scope import Scope

Row = tuple[str, str, str]  # mutant, status, the change it made ("" when the report does not say)


def _rows(text: str, tool: MutationTool) -> list[Row]:
    rows: list[Row] = []
    for line in text.splitlines():
        head, _, change = line.partition("\t")
        name, _, status = head.strip().partition(": ")
        if status and status not in tool.ignored:
            rows.append((name, status, change.strip()))
    if not rows:
        raise GauntletError(tool.empty)
    if all(status in tool.never_ran for _, status, _ in rows):
        raise GauntletError(tool.broken)
    return rows


def _in_scope(where: Where | None, caught: bool, scope: Scope) -> bool:
    """A mutant nobody can place is judged only when it survived: it can lower a scoped score, never raise it."""
    if where is None:
        return not (scope.entries and caught)
    return scope.overlaps(*where)


def _finding(row: Row, where: Where | None) -> str:
    name, status, change = row
    place = f"{where[0]}:{where[1]}" if where else ""
    prefix = f"{place}: " if place and not name.startswith(f"{place} ") else ""
    return f"{prefix}{name}: {status}" + (f" [{change}]" if change else "")


def check(text: str, tool: MutationTool, root: Path, scope: Scope) -> Mutation:
    rows = _rows(text, tool)
    places = tool.locate([name for name, _, _ in rows], root)
    seen = [r for r in rows if _in_scope(places.get(r[0]), r[1] in tool.caught, scope)]
    if not seen:
        raise GauntletError("no mutants in scope: --only matched no code the mutation tool changed")
    survivors = [_finding(r, places.get(r[0])) for r in seen if r[1] not in tool.caught]
    caught = len(seen) - len(survivors)
    return Mutation(100 * caught / len(seen), survivors, caught, len(seen))
