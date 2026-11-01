from pathlib import Path

import pytest

from gauntlet.clean import Finding, check, crap_score, function_findings
from gauntlet.languages import TABLE
from gauntlet.scope import Scope, parse

PY = TABLE["python"]
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


# ---- the score
def test_fully_covered_equals_complexity() -> None:
    assert crap_score(complexity=5, coverage=1.0) == 5


def test_uncovered_is_quadratic_plus_complexity() -> None:
    assert crap_score(complexity=4, coverage=0.0) == 4**2 + 4


def test_partial_coverage() -> None:
    assert crap_score(complexity=10, coverage=0.5) == pytest.approx(10**2 * 0.5**3 + 10)


@pytest.mark.parametrize("coverage", [-0.1, 1.1])
def test_rejects_coverage_out_of_range(coverage: float) -> None:
    with pytest.raises(ValueError, match="coverage"):
        crap_score(complexity=1, coverage=coverage)


# ---- per function
def test_covered_function_scores_its_complexity() -> None:
    (f,) = function_findings("m.py", SIMPLE, {1: 1, 2: 1})
    assert f == Finding(name="f", line=1, complexity=1, coverage=1.0, crap=1.0)


def test_only_executable_lines_count_toward_coverage() -> None:
    hits = {1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0}  # lines 1-8, one hit
    (f,) = function_findings("m.py", BRANCHY, hits)
    assert f.complexity == 4
    assert f.coverage == pytest.approx(1 / 8)
    assert f.crap == pytest.approx(4**2 * (1 - 1 / 8) ** 3 + 4)


def test_lines_that_are_not_code_do_not_dilute_coverage() -> None:
    (f,) = function_findings("m.py", BRANCHY, {2: 1, 3: 1})  # only 2 executable lines known, both hit
    assert f.coverage == 1.0


def test_function_without_executable_lines_counts_as_covered() -> None:
    (f,) = function_findings("m.py", SIMPLE, {})
    assert f.coverage == 1.0


def test_methods_are_named_with_their_class() -> None:
    (f,) = function_findings("m.py", "class A:\n    def m(self):\n        return 1\n", {2: 1, 3: 1})
    assert f.name.endswith("m")
    assert f.line == 2


def test_coverage_is_per_function_not_per_file() -> None:
    src = SIMPLE + "\n" + BRANCHY.replace("g", "h", 1)
    hits = {1: 1, 2: 1, **{n: 0 for n in range(4, 12)}}
    covered, risky = function_findings("m.py", src, hits)
    assert (covered.coverage, risky.coverage) == (1.0, 0.0)


def test_adjacent_functions_do_not_share_lines() -> None:
    src = "def f():\n    return 1\ndef g():\n    return 2\n"
    f, g = function_findings("m.py", src, {1: 1, 2: 1, 3: 0, 4: 0})
    assert (f.coverage, g.coverage) == (1.0, 0.0)


# ---- the gate over a project
def project(root: Path, source: str = SIMPLE, name: str = "mod.py") -> Path:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(source)
    return root


def test_check_passes_when_all_under_threshold(tmp_path: Path) -> None:
    result = check(project(tmp_path), {"mod.py": {1: 1, 2: 1}}, PY, 8, Scope())
    assert (result.evaluated, result.offenders) == (1, [])


def test_check_reports_offenders_with_their_path(tmp_path: Path) -> None:
    hits = {1: 1, **{n: 0 for n in range(2, 9)}}
    ((path, f),) = check(project(tmp_path, BRANCHY), {"mod.py": hits}, PY, 8, Scope()).offenders
    assert (path, f.name) == ("mod.py", "g")


def test_threshold_is_inclusive(tmp_path: Path) -> None:
    project(tmp_path)
    assert check(tmp_path, {"mod.py": {1: 1, 2: 1}}, PY, 1, Scope()).offenders == []
    assert len(check(tmp_path, {"mod.py": {1: 1, 2: 1}}, PY, 0, Scope()).offenders) == 1


def test_scope_limits_what_is_evaluated_and_reported(tmp_path: Path) -> None:
    project(tmp_path, SIMPLE + "\n" + BRANCHY.replace("g", "h", 1))
    hits = {1: 1, 2: 1, **{n: 0 for n in range(4, 12)}}
    assert check(tmp_path, {"mod.py": hits}, PY, 8, parse(["mod.py"])).evaluated == 2
    assert check(tmp_path, {"mod.py": hits}, PY, 8, parse(["mod.py:1-2"])).evaluated == 1
    assert check(tmp_path, {"mod.py": hits}, PY, 8, parse(["other.py"])).evaluated == 0


def test_every_measured_file_is_evaluated(tmp_path: Path) -> None:
    project(tmp_path, BRANCHY, "a.py")
    project(tmp_path, BRANCHY, "pkg/b.py")
    cov = {n: {1: 1, **{k: 0 for k in range(2, 9)}} for n in ("a.py", "pkg/b.py")}
    assert [p for p, _ in check(tmp_path, cov, PY, 8, Scope()).offenders] == ["a.py", "pkg/b.py"]


def test_coverage_paths_that_belong_to_no_source_file_are_ignored(tmp_path: Path) -> None:
    result = check(project(tmp_path), {"mod.py": {1: 1}, "/usr/include/stdio.h": {1: 0}}, PY, 8, Scope())
    assert result.evaluated == 1


def test_coverage_paths_cannot_climb_out_of_the_project(tmp_path: Path) -> None:
    root = tmp_path / "root"
    project(root)
    with pytest.raises(ValueError, match="escapes the project root"):
        check(root, {"../secret.py": {1: 1}}, PY, 8, Scope())


def test_oversized_source_is_rejected(tmp_path: Path) -> None:
    project(tmp_path, "x = 1\n" * 10)
    with pytest.raises(ValueError, match="byte limit"):
        check(tmp_path, {"mod.py": {1: 1}}, PY, 8, Scope(), max_bytes=10)


def test_source_that_is_not_text_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        check(tmp_path, {"mod.py": {1: 1}}, PY, 8, Scope())


def test_a_source_file_the_report_never_mentions_counts_as_uncovered(tmp_path: Path) -> None:
    project(tmp_path, BRANCHY, "a.py")
    project(tmp_path, BRANCHY, "hidden.py")
    cov = {"a.py": {1: 1, **{k: 1 for k in range(2, 9)}}}
    ((path, f),) = check(tmp_path, cov, PY, 8, Scope()).offenders
    assert (path, f.coverage) == ("hidden.py", 0.0)


def test_test_files_are_not_held_to_the_limit(tmp_path: Path) -> None:
    project(tmp_path, SIMPLE)
    project(tmp_path, BRANCHY, "tests/test_mod.py")
    result = check(tmp_path, {"mod.py": {1: 1, 2: 1}}, PY, 8, Scope())
    assert (result.evaluated, result.offenders) == (1, [])


@pytest.mark.parametrize("name", ["src/test_evil.py", "src/tests/evil.py", "pkg/conftest.py", "src/evil_test.py"])
def test_a_test_looking_name_inside_the_source_tree_is_still_checked(tmp_path: Path, name: str) -> None:
    project(tmp_path)
    project(tmp_path, BRANCHY, name)
    ((path, _),) = check(tmp_path, {"mod.py": {1: 1, 2: 1}}, PY, 8, Scope()).offenders
    assert path == name


def test_a_report_matching_no_source_file_is_an_error_not_a_pass(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mentions no source file"):
        check(project(tmp_path), {}, PY, 8, Scope())


def test_python_stub_files_with_no_functions_stay_clean() -> None:
    assert function_findings("stub.py", "X = 1\nclass A: ...\n", None) == []


def test_a_function_with_branches_but_no_measured_lines_counts_as_uncovered(tmp_path: Path) -> None:
    project(tmp_path, SIMPLE + "\n" + BRANCHY.replace("g", "h", 1))
    hits = {1: 1, 2: 1}  # the branchy function has no lines in the report: hidden, not trivially covered
    ((_, f),) = check(tmp_path, {"mod.py": hits}, PY, 8, Scope()).offenders
    assert (f.name, f.coverage) == ("h", 0.0)
    assert check(tmp_path, {"mod.py": hits}, PY, 8, Scope()).evaluated == 2
