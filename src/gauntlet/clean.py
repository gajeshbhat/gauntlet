"""Clean gate: CRAP score per function = complexity (read by lizard, any language) x coverage of its own lines."""

import re
from dataclasses import dataclass
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


def function_findings(filename: str, source: str, hits: dict[int, int] | None) -> list[Finding]:
    """One finding per function in `source`; `hits` maps the executable lines of the file to their hit counts.

    `hits` of None means the coverage report never mentions the file: nothing exercised it, so it counts as 0%."""
    findings: list[Finding] = []
    functions = cast(
        "list[Any]",
        lizard.analyze_file.analyze_source_code(filename, source).function_list,  # pyright: ignore[reportUnknownMemberType]
    )
    for fn in functions:
        executable = [n for n in range(fn.start_line, fn.end_line + 1) if hits is None or n in hits]
        covered = 0 if hits is None else sum(hits[n] > 0 for n in executable)
        coverage = covered / len(executable) if executable else 1.0
        complexity = int(fn.cyclomatic_complexity)
        findings.append(
            Finding(str(fn.name), int(fn.start_line), complexity, coverage, crap_score(complexity, coverage))
        )
    return findings


def _measure(root: Path, rel: str, hits: dict[int, int] | None, scope: Scope, max_bytes: int) -> list[Finding]:
    found = function_findings(rel, read_text(inside(root, rel), max_bytes), hits)
    return [f for f in found if scope.contains(rel, f.line)]


def _measured(lines: linecov.Lines, files: list[str]) -> linecov.Lines:
    """The coverage report keyed by project-relative source path; a report that names none of them is wrong."""
    found = {rel: hits for key, hits in lines.items() if (rel := linecov.locate(key, files)) is not None}
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
    measured = _measured(lines, files)
    evaluated = 0
    offenders: list[tuple[str, Finding]] = []
    for rel in (f for f in files if not re.search(language.tests, f)):
        found = _measure(root, rel, measured.get(rel), scope, max_bytes)
        evaluated += len(found)
        offenders += [(rel, f) for f in found if f.crap > crap_max]
    return CleanResult(evaluated, offenders)
