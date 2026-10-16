import json
from pathlib import Path

import pytest

from gauntlet.clean import Finding, check, function_findings

SIMPLE = "def f(x):\n    return x\n"
BRANCHY = (
    "def g(x):\n"
    "    if x == 1:\n"
    "        return 1\n"
    "    if x == 2:\n"
    "        return 2\n"
    "    if x == 3:\n"
    "        return 3\n"
    "    return 0\n"
)  # complexity 4, lines 1-8


def test_covered_function_scores_its_complexity() -> None:
    (f,) = function_findings(SIMPLE, executed={1, 2}, missing=set())
    assert f == Finding(name="f", line=1, complexity=1, coverage=1.0, crap=1.0)


def test_uncovered_branchy_function_is_quadratic() -> None:
    (f,) = function_findings(BRANCHY, executed={1}, missing={2, 3, 4, 5, 6, 7, 8})
    assert f.complexity == 4
    assert f.crap == pytest.approx(4**2 * (1 - 1 / 8) ** 3 + 4)


def test_class_methods_reported_by_qualified_name() -> None:
    src = "class A:\n    def m(self):\n        return 1\n"
    (f,) = function_findings(src, executed={1, 2, 3}, missing=set())
    assert f.name == "A.m"
    assert f.line == 2


def test_function_without_executable_lines_counts_as_covered() -> None:
    (f,) = function_findings(SIMPLE, executed=set(), missing=set())
    assert f.coverage == 1.0


def write_project(root: Path, source: str, executed: list[int], missing: list[int]) -> None:
    (root / "mod.py").write_text(source)
    cov = {"files": {"mod.py": {"executed_lines": executed, "missing_lines": missing}}}
    (root / "coverage.json").write_text(json.dumps(cov))


def test_check_passes_when_all_under_threshold(tmp_path: Path) -> None:
    write_project(tmp_path, SIMPLE, [1, 2], [])
    assert check(tmp_path, tmp_path / "coverage.json", crap_max=8) == []


def test_check_reports_offenders_with_path(tmp_path: Path) -> None:
    write_project(tmp_path, BRANCHY, [1], [2, 3, 4, 5, 6, 7, 8])
    ((path, f),) = check(tmp_path, tmp_path / "coverage.json", crap_max=8)
    assert path == "mod.py"
    assert f.name == "g"


def test_threshold_is_inclusive(tmp_path: Path) -> None:
    write_project(tmp_path, SIMPLE, [1, 2], [])
    assert check(tmp_path, tmp_path / "coverage.json", crap_max=1) == []
    assert len(check(tmp_path, tmp_path / "coverage.json", crap_max=0)) == 1


def test_missing_coverage_file_explains_how_to_make_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="--cov-report=json"):
        check(tmp_path, tmp_path / "coverage.json", crap_max=8)
