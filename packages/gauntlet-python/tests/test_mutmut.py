from pathlib import Path

import pytest

from gauntlet import harden
from gauntlet.results import Mutation
from gauntlet.scope import Scope, parse
from gauntlet_python.mutmut import TOOL, locate

RESULTS = """
    pkg.x_a__mutmut_1: killed
    pkg.x_a__mutmut_2: survived
    pkg.x_b__mutmut_1: timeout
    pkg.x_b__mutmut_2: skipped
    pkg.x_c__mutmut_1: no tests
"""

MODULE = """import os


def first(x):
    return x


class Box:
    size = 1

    def area(self):
        return (
            self.size
        )

    async def later(self):
        return 1


@staticmethod
async def last():
    return os.sep
"""


def check(results: str, root: Path, scope: Scope = Scope()) -> Mutation:  # noqa: B008
    return harden.check(results, TOOL, root, scope)


def test_score_counts_killed_and_timeout_and_ignores_skipped(tmp_path: Path) -> None:
    result = check(RESULTS, tmp_path)
    assert (result.caught, result.total, result.pct) == (2, 4, 50.0)
    assert result.survivors == ["pkg.x_a__mutmut_2: survived", "pkg.x_c__mutmut_1: no tests"]


def test_score_of_nothing_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"^no mutants found; is \[tool.mutmut\] configured in the target repo\?$"):
        check("", tmp_path)


def test_segfaults_count_as_caught(tmp_path: Path) -> None:
    assert check("a: segfault\nb: survived\n", tmp_path).pct == 50.0


def test_mutants_that_were_all_never_checked_mean_mutmut_did_not_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"^mutmut checked no mutant: its tests never ran.*`mutmut run` in the proj"):
        check("pkg.x_a__mutmut_1: not checked\npkg.x_a__mutmut_2: not checked\n", tmp_path)


def test_a_few_unchecked_mutants_among_checked_ones_are_survivors_not_an_error(tmp_path: Path) -> None:
    assert check("pkg.x_a__mutmut_1: killed\npkg.x_a__mutmut_2: not checked\n", tmp_path).pct == 50.0


def test_the_report_and_how_to_make_it() -> None:
    assert TOOL.artifact == "mutmut-results.txt"
    assert TOOL.how == "mutmut run && mutmut results --all true > mutmut-results.txt (or: gauntlet run)"


@pytest.mark.parametrize("rel", ["pkg/mod.py", "src/pkg/mod.py", "source/pkg/mod.py", "pkg/mod/__init__.py"])
def test_a_mutant_is_in_the_function_its_name_spells(tmp_path: Path, rel: str) -> None:
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text(MODULE)
    names = [
        "pkg.mod.x_first__mutmut_1",
        "pkg.mod.xǁBoxǁarea__mutmut_2",
        "pkg.mod.xǁBoxǁlater__mutmut_1",
        "pkg.mod.x_last__mutmut_12",
    ]
    assert locate(names, tmp_path) == {
        names[0]: (rel, 4, 5),
        names[1]: (rel, 11, 14),
        names[2]: (rel, 16, 17),
        names[3]: (rel, 21, 22),  # the `def` line, not the decorator's
    }


def test_the_module_directly_under_the_root_wins_over_one_under_src(tmp_path: Path) -> None:
    for rel in ("src/pkg.py", "pkg.py"):
        (tmp_path / rel).parent.mkdir(exist_ok=True)
        (tmp_path / rel).write_text("def f():\n    return 1\n")
    assert locate(["pkg.x_f__mutmut_1"], tmp_path) == {"pkg.x_f__mutmut_1": ("pkg.py", 1, 2)}


def test_a_name_that_points_at_no_function_has_no_place(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(MODULE)
    (tmp_path / "pkg" / "broken.py").write_text("def f(:\n")
    (tmp_path / "pkg" / "nul.py").write_text("x = '\0'\n")
    names = [
        "x_first__mutmut_1",  # no module
        "pkg.mod.x_gone__mutmut_1",  # no such function
        "pkg.mod.x_area__mutmut_1",  # a method is not a function
        "pkg.mod.xǁBoxǁsize__mutmut_1",  # not a method
        "pkg.missing.x_f__mutmut_1",  # no such file
        "pkg.broken.x_f__mutmut_1",  # a file Python cannot parse
        "pkg.nul.x_f__mutmut_1",
        "pkg.x_f__mutmut_1",  # a directory without __init__.py
    ]
    assert locate(names, tmp_path) == {}


def test_the_mutant_number_is_what_follows_the_last_marker_and_a_stray_name_stops_nothing(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def odd__mutmut_name():\n    return 1\n")
    names = ["stray", "m.x_odd__mutmut_name__mutmut_4"]
    assert locate(names, tmp_path) == {names[1]: ("m.py", 1, 2)}


def test_a_name_may_not_point_outside_the_project(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes the project root"):
        locate(["/etc/x.x_f__mutmut_1"], tmp_path)


def test_each_module_is_read_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "m.py").write_text("def f():\n    return 1\n")
    reads: list[Path] = []
    real = Path.read_text

    def read(self: Path) -> str:
        reads.append(self)
        return real(self)

    monkeypatch.setattr(Path, "read_text", read)
    names = ["m.x_f__mutmut_1", "m.x_f__mutmut_2", "gone.x_f__mutmut_1", "gone.x_f__mutmut_2"]
    assert list(locate(names, tmp_path)) == names[:2]
    assert reads == [tmp_path / "m.py"]


def test_survivors_say_where_and_a_scope_keeps_only_its_functions(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text(MODULE)
    results = (
        "pkg.mod.x_first__mutmut_1: survived\t-    return x +    return None\n"
        "pkg.mod.xǁBoxǁarea__mutmut_1: killed\n"
        "pkg.mod.xǁBoxǁarea__mutmut_2: survived\n"
    )
    assert check(results, tmp_path).survivors == [
        "src/pkg/mod.py:4: pkg.mod.x_first__mutmut_1: survived [-    return x +    return None]",
        "src/pkg/mod.py:11: pkg.mod.xǁBoxǁarea__mutmut_2: survived",
    ]
    scoped = check(results, tmp_path, parse(["src/pkg/mod.py:13-13"]))  # a line inside Box.area
    assert (scoped.caught, scoped.total) == (1, 2)
    assert scoped.survivors == ["src/pkg/mod.py:11: pkg.mod.xǁBoxǁarea__mutmut_2: survived"]
