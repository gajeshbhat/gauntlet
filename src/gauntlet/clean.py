"""Clean gate: CRAP score per function = complexity (read by lizard, any language) x coverage of its own lines."""

import re
from dataclasses import dataclass
from math import inf
from pathlib import Path
from typing import Any, cast

import lizard  # pyright: ignore[reportMissingTypeStubs]

from gauntlet import linecov
from gauntlet.languages import Language
from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text, source_files
from gauntlet.scope import Scope


def crap_score(complexity: int, coverage: float) -> float:
    """complexity^2 * (1 - coverage)^3 + complexity: risky code is complex and untested."""
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f"coverage must be within 0..1, got {coverage}")
    return complexity**2 * (1 - coverage) ** 3 + complexity


@dataclass(frozen=True)
class Finding:
    name: str
    line: int
    complexity: int
    coverage: float
    crap: float


@dataclass(frozen=True)
class CleanResult:
    evaluated: int  # functions looked at; 0 means the gate saw nothing and must not pass
    offenders: list[tuple[str, Finding]]


DIRECTIVE = re.compile(r"\s*(?:library|import|export|part)\s+['\"\w][^;]*;\s*$")
TOKEN = re.compile(  # strings stay (they may hold "//"); comments go, keeping their line breaks
    r"""('''|\"\"\").*?\1|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/""", re.DOTALL
)
UNREAD = "(unread code)"


def _code_lines(source: str) -> list[int]:
    """Line numbers holding anything but comments, blanks and whole import/export directives."""
    bare = TOKEN.sub(lambda m: "\n" * m[0].count("\n") if m[0].startswith(("//", "/*")) else m[0], source)
    return [n for n, line in enumerate(bare.splitlines(), 1) if line.strip() and not DIRECTIVE.match(line)]


def _runs(numbers: list[int]) -> list[list[int]]:
    """Consecutive line numbers grouped, so each stretch of unread code is judged against a line-ranged scope alone."""
    runs: list[list[int]] = []
    for n in sorted(numbers):
        if runs and n == runs[-1][-1] + 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    return runs


def _unread_findings(lines: list[int], coverage: float) -> list[Finding]:
    return [Finding(UNREAD, run[0], 0, coverage, inf) for run in _runs(lines)]


def _unread(source: str, hits: dict[int, int] | None, seen: set[int]) -> list[Finding]:
    """Code the reader did not attribute to any function (`seen` holds the lines it did) must not pass unseen.

    Measured file: executable lines outside every function that never ran. Unmeasured file: any code outside them."""
    if hits is None:
        return _unread_findings([n for n in _code_lines(source) if n not in seen], 0.0)
    missed = [n for n, count in hits.items() if count == 0 and n not in seen]
    return _unread_findings(missed, 1 - len(missed) / len(hits) if hits else 1.0)


def _functions(filename: str, source: str, parse_as: str) -> list[Any]:
    name = str(Path(filename).with_suffix(f".{parse_as}")) if parse_as else filename
    return cast(
        "list[Any]",
        lizard.analyze_file.analyze_source_code(name, source).function_list,  # pyright: ignore[reportUnknownMemberType]
    )


def _finding(fn: Any, hits: dict[int, int] | None) -> Finding:  # noqa: ANN401
    executable = [n for n in range(fn.start_line, fn.end_line + 1) if hits is None or n in hits]
    covered = 0 if hits is None else sum(hits[n] > 0 for n in executable)
    complexity = int(fn.cyclomatic_complexity)
    coverage = covered / len(executable) if executable else float(complexity == 1)  # branches but no lines: hidden
    return Finding(str(fn.name), int(fn.start_line), complexity, coverage, crap_score(complexity, coverage))


def function_findings(filename: str, source: str, hits: dict[int, int] | None, parse_as: str = "") -> list[Finding]:
    """One finding per function in `source`; `hits` maps the executable lines of the file to their hit counts.

    `hits` of None means the coverage report never mentions the file: nothing exercised it, so it counts as 0%.
    `parse_as` names another language whose lizard reader reads this file; its approximations fail closed:
    lines the reader attributes to no function are judged as one unread block (see `_unread`)."""
    functions = _functions(filename, source, parse_as)
    found = [_finding(fn, hits) for fn in functions]
    if not parse_as:
        return found
    seen = {n for fn in functions for n in range(fn.start_line, fn.end_line + 1)}
    return found + _unread(source, hits, seen)


def _measure(
    root: Path, rel: str, hits: dict[int, int] | None, scope: Scope, max_bytes: int, parse_as: str
) -> list[Finding]:
    found = function_findings(rel, read_text(inside(root, rel), max_bytes), hits, parse_as)
    return [f for f in found if scope.contains(rel, f.line)]


def _measured(lines: linecov.Lines, files: list[str], prefixed: bool) -> linecov.Lines:
    """The coverage report keyed by project-relative source path; a report that names none of them is wrong."""
    found = {rel: hits for key, hits in lines.items() if (rel := linecov.locate(key, files, prefixed)) is not None}
    if not found:
        raise ValueError("the coverage report mentions no source file of this project: wrong report or empty tests")
    return found


def check(
    root: Path,
    lines: linecov.Lines,
    language: Language,
    crap_max: float,
    scope: Scope,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> CleanResult:
    files = source_files(root, language.suffixes)
    measured = _measured(lines, files, language.coverage_format == "gocover")
    evaluated = 0
    offenders: list[tuple[str, Finding]] = []
    for rel in (f for f in files if not re.search(language.tests, f)):
        found = _measure(root, rel, measured.get(rel), scope, max_bytes, language.parse_as)
        evaluated += len(found)
        offenders += [(rel, f) for f in found if f.crap > crap_max]
    return CleanResult(evaluated, offenders)
