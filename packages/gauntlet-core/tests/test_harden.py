from dataclasses import replace
from pathlib import Path

import pytest
from fakelang import tool

from gauntlet.harden import check
from gauntlet.plugin import Where
from gauntlet.results import Mutation
from gauntlet.scope import Scope, parse

TOOL = tool("run the fake mutator")
ROOT = Path("unused")


def judge(text: str, *only: str) -> Mutation:
    return check(text, TOOL, ROOT, parse(list(only)))


def test_the_score_is_the_share_of_mutants_the_tests_caught() -> None:
    result = judge("a: killed\nb: survived\nc: killed\nd: not checked\n")
    assert result == Mutation(50.0, ["b: survived", "d: not checked"], 2, 4)


def test_lines_without_a_status_and_ignored_statuses_are_no_mutants() -> None:
    result = judge("Mutant results\n\n   a: killed  \nb: skipped\nc:\n")
    assert (result.caught, result.total) == (1, 1)


def test_a_report_without_mutants_is_an_error() -> None:
    with pytest.raises(ValueError, match="^no mutants found$"):
        judge("b: skipped\n")


def test_a_report_where_no_mutant_ever_ran_is_an_error() -> None:
    with pytest.raises(ValueError, match="^the fake mutator checked no mutant$"):
        judge("a: not checked\nb: not checked\n")
    assert judge("a: not checked\nb: survived\n").pct == 0.0  # one ran: a real, failing score


def test_a_survivor_says_where_its_code_is_and_what_it_changed() -> None:
    result = judge("m.py@3-9 f: survived\t `a < b` -> `a <= b` \nm.py@3-9 g: killed\tx\nplain: survived\tswap\n")
    assert result.survivors == ["m.py:3: m.py@3-9 f: survived [`a < b` -> `a <= b`]", "plain: survived [swap]"]


def test_a_name_that_already_starts_with_its_place_is_not_prefixed() -> None:
    def on_line_three(names: list[str], root: Path) -> dict[str, Where]:  # noqa: ARG001
        return {n: ("m.py", 3, 3) for n in names}

    where = replace(TOOL, locate=on_line_three)
    assert check("m.py:3 op: survived\nm.py:30 op: survived\n", where, ROOT, Scope()).survivors == [
        "m.py:3 op: survived",
        "m.py:3: m.py:30 op: survived",
    ]


def test_a_scope_judges_only_the_mutants_whose_code_it_touches() -> None:
    text = "m.py@3-9 f: killed\nm.py@3-9 g: survived\nm.py@20-30 h: survived\nn.py@3-9 i: killed\n"
    assert judge(text) == Mutation(50.0, ["m.py:3: m.py@3-9 g: survived", "m.py:20: m.py@20-30 h: survived"], 2, 4)
    assert judge(text, "m.py:9-12") == Mutation(50.0, ["m.py:3: m.py@3-9 g: survived"], 1, 2)
    assert judge(text, "n.py") == Mutation(100.0, [], 1, 1)


def test_under_a_scope_a_mutant_nobody_can_place_counts_only_when_it_survived() -> None:
    text = "m.py@3-9 f: killed\nlost: killed\nstray: survived\n"
    assert judge(text, "m.py") == Mutation(50.0, ["stray: survived"], 1, 2)
    assert judge(text).total == 3  # without a scope every mutant counts


def test_a_scope_that_touches_no_mutant_is_an_error() -> None:
    with pytest.raises(ValueError, match="^no mutants in scope: --only matched no code the mutation tool changed$"):
        judge("m.py@3-9 f: killed\nlost: killed\n", "other.py")


def test_the_tool_is_asked_once_for_every_mutant_with_the_project_root(tmp_path: Path) -> None:
    asked: list[tuple[list[str], Path]] = []

    def nowhere(names: list[str], root: Path) -> dict[str, Where]:
        asked.append((names, root))
        return {}

    spy = replace(TOOL, locate=nowhere)
    check("a: killed\nb: survived\nc: skipped\n", spy, tmp_path, Scope())
    assert asked == [(["a", "b"], tmp_path)]
