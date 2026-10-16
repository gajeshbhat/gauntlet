"""Clean gate: fail functions whose CRAP score exceeds the configured maximum."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from radon.complexity import cc_visit  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]

from gauntlet.crap import crap_score
from gauntlet.safefs import MAX_ARTIFACT_BYTES, MAX_SOURCE_BYTES, inside, read_text
from gauntlet.scope import Scope


@dataclass(frozen=True)
class Finding:
    name: str
    line: int
    complexity: int
    coverage: float
    crap: float


def function_findings(source: str, executed: set[int], missing: set[int]) -> list[Finding]:
    findings: list[Finding] = []
    blocks = cast("list[Any]", cc_visit(source))  # pragma: no mutate (radon ships no stubs)
    for block in blocks:
        if type(block).__name__ != "Function":
            continue  # radon also yields Class blocks; their methods come through as Functions
        span = set(range(block.lineno, block.endline + 1))
        hit, miss = len(executed & span), len(missing & span)
        coverage = hit / (hit + miss) if hit + miss else 1.0
        name = f"{block.classname}.{block.name}" if block.classname else block.name
        crap = crap_score(block.complexity, coverage)
        findings.append(Finding(name, block.lineno, block.complexity, coverage, crap))
    return findings


@dataclass(frozen=True)
class CleanResult:
    evaluated: int  # functions looked at; 0 means the gate saw nothing and must not pass
    offenders: list[tuple[str, Finding]]


def _analyse(rel: str, source: str, data: dict[str, Any]) -> list[Finding]:
    try:
        return function_findings(source, set(data["executed_lines"]), set(data["missing_lines"]))
    except (SyntaxError, RecursionError, MemoryError, ValueError) as e:
        raise ValueError(f"cannot analyse {rel}: {type(e).__name__}") from None


def check(
    root: Path, coverage_json: Path, crap_max: float, scope: Scope, max_bytes: int = MAX_SOURCE_BYTES
) -> CleanResult:
    if not coverage_json.exists():
        raise FileNotFoundError(
            f"{coverage_json} not found; run your tests with `pytest --cov --cov-report=json` first"
        )
    files = json.loads(read_text(coverage_json, MAX_ARTIFACT_BYTES))["files"]
    evaluated = 0
    offenders: list[tuple[str, Finding]] = []
    for rel, data in files.items():
        found = [f for f in _analyse(rel, read_text(inside(root, rel), max_bytes), data) if scope.contains(rel, f.line)]
        evaluated += len(found)
        offenders += [(rel, f) for f in found if f.crap > crap_max]
    return CleanResult(evaluated, offenders)
