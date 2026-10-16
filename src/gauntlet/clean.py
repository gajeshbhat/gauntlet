"""Clean gate: fail functions whose CRAP score exceeds the configured maximum."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from radon.complexity import cc_visit  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]

from gauntlet.crap import crap_score


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


def check(root: Path, coverage_json: Path, crap_max: float) -> list[tuple[str, Finding]]:
    if not coverage_json.exists():
        raise FileNotFoundError(
            f"{coverage_json} not found; run your tests with `pytest --cov --cov-report=json` first"
        )
    files = json.loads(coverage_json.read_text())["files"]
    offenders: list[tuple[str, Finding]] = []
    for rel, data in files.items():
        source = (root / rel).read_text()
        executed, missing = set(data["executed_lines"]), set(data["missing_lines"])
        offenders += [(rel, f) for f in function_findings(source, executed, missing) if f.crap > crap_max]
    return offenders
