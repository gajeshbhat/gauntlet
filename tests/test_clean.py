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


def test_coverage_is_per_function_not_per_file() -> None:
    src = SIMPLE + "\n" + BRANCHY.replace("g", "h", 1)
    covered, risky = function_findings(src, executed={1, 2}, missing=set(range(4, 12)))
    assert covered.coverage == 1.0
    assert risky.coverage == 0.0


def test_half_covered_function() -> None:
    (f,) = function_findings(SIMPLE, executed={1}, missing={2})
    assert f.coverage == 0.5


def test_check_collects_offenders_from_every_file(tmp_path: Path) -> None:
    files = {}
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_text(BRANCHY)
        files[name] = {"executed_lines": [1], "missing_lines": [2, 3, 4, 5, 6, 7, 8]}
    (tmp_path / "coverage.json").write_text(json.dumps({"files": files}))
    paths = [p for p, _ in check(tmp_path, tmp_path / "coverage.json", crap_max=8)]
    assert paths == ["a.py", "b.py"]


def test_adjacent_functions_do_not_share_lines() -> None:
    src = "def f():\n    return 1\ndef g():\n    return 2\n"
    f, g = function_findings(src, executed={1, 2}, missing={3, 4})
    assert (f.coverage, g.coverage) == (1.0, 0.0)
