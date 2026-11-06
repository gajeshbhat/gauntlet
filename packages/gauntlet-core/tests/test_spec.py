from pathlib import Path

import pytest

from gauntlet.spec import Scenario, check, parse

GOOD = """\
# comment
Feature: Rate limiting
  Background:
    Given a limiter allowing 2 requests per second

  @test(tests/test_limiter.py::test_allows_two)
  Scenario: Two requests pass
    When 2 requests arrive
    Then both are allowed

  @test(tests/test_limiter.py)
  Scenario Outline: Limits
    Given a limit of <limit>
    When <n> requests arrive
    Then <allowed> are allowed

    Examples:
      | limit | n | allowed |
      | 2     | 3 | 2       |
"""


def project(root: Path, feature: str = GOOD, test_text: str = "def test_allows_two(): pass\n") -> Path:
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_limiter.py").write_text(test_text)
    path = root / "spec.feature"
    path.write_text(feature)
    return path


def test_parse_reads_scenarios_tags_and_examples() -> None:
    feature = parse(GOOD)
    assert feature.name == "Rate limiting"
    assert [s.name for s in feature.scenarios] == ["Two requests pass", "Limits"]
    first, second = feature.scenarios
    assert first.tags == ("test(tests/test_limiter.py::test_allows_two)",)
    assert [k for k, _ in first.steps] == ["When", "Then"]
    assert second.outline
    assert second.examples == (("limit", "n", "allowed"), ("2", "3", "2"))
    assert feature.background == ("Given a limiter allowing 2 requests per second",)


def test_a_good_spec_has_no_problems(tmp_path: Path) -> None:
    path = project(tmp_path)
    assert check(path, tmp_path) == []


def test_and_but_inherit_the_previous_keyword() -> None:
    feature = parse("Feature: x\n  @test(a.py)\n  Scenario: s\n    When a\n    And b\n    Then c\n    But d\n")
    assert [k for k, _ in feature.scenarios[0].steps] == ["When", "When", "Then", "Then"]


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("Scenario: s\n  When a\n  Then b\n", "no Feature"),
        ("Feature: a\nFeature: b\n", "more than one Feature"),
        ("Feature: a\n  @test(t.py)\n  Scenario: s\n    Given a\n    Then b\n", "'s' has no When"),
        ("Feature: a\n  @test(t.py)\n  Scenario: s\n    Given a\n    When b\n", "'s' has no Then"),
        ("Feature: a\n  Scenario: s\n    When a\n    Then b\n", "'s' has no @test(...) tag"),
        (
            "Feature: a\n  @test(t.py)\n  Scenario Outline: o\n    When <x>\n    Then ok\n",
            "'o' is an outline without Examples",
        ),
        (
            "Feature: a\n  @test(t.py)\n  Scenario Outline: o\n    When <x>\n    Then ok\n    Examples:\n      | y |\n      | 1 |\n",
            "'o' uses <x> but Examples has no such column",
        ),
        (
            "Feature: a\n  @test(t.py)\n  Scenario: s\n    When x\n    Then y\n    Examples:\n      | a |\n      | 1 |\n",
            "'s' has Examples but is not an outline",
        ),
        (
            "Feature: a\n  @test(t.py)\n  Scenario Outline: o\n    When <x>\n    Then ok\n    Examples:\n      | x |\n",
            "'o' has an Examples table with no rows",
        ),
        (
            "Feature: a\n  @test(t.py)\n  Scenario Outline: s\n    When <a>\n    Then y\n    Examples:\n      | a |\n      | 1 | 2 |\n",
            "row 2 has 2 cells, header has 1",
        ),
        ("Feature: a\n  Scenario: s\n  gibberish\n", "line 3: not understood"),
        ("Feature: a\n  Then orphan\n", "line 2: step outside a scenario"),
        ("Feature: a\n  | a |\n", "line 2: table row outside Examples"),
        (
            "Feature: a\n  @test(t.py)\n  Scenario: s\n    When x\n    | a |\n    Then y\n",
            "line 5: table row outside Examples",
        ),
        ("Feature:\n", "Feature has no name"),
        ("Feature: a\n  Scenario:\n    When x\n    Then y\n", "Scenario has no name"),
    ],
)
def test_malformed_specs_are_reported(tmp_path: Path, text: str, problem: str) -> None:
    path = project(tmp_path, text)
    problems = check(path, tmp_path)
    assert any(problem in p for p in problems), problems


def test_every_problem_is_listed_not_just_the_first(tmp_path: Path) -> None:
    text = "Feature: a\n  Scenario: s\n    Given a\n"
    problems = check(project(tmp_path, text), tmp_path)
    assert len(problems) == 3  # no When, no Then, no @test tag


def test_tags_must_point_at_a_real_test(tmp_path: Path) -> None:
    text = GOOD.replace("tests/test_limiter.py::test_allows_two", "tests/test_limiter.py::test_missing")
    assert any("test_missing is not in tests/test_limiter.py" in p for p in check(project(tmp_path, text), tmp_path))
    text = GOOD.replace("tests/test_limiter.py::test_allows_two", "tests/nope.py")
    assert any("tests/nope.py does not exist" in p for p in check(project(tmp_path, text), tmp_path))


def test_tags_cannot_escape_the_project(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.py").write_text("def test_x(): pass\n")
    text = GOOD.replace("tests/test_limiter.py::test_allows_two", "../outside.py::test_x")
    assert any("escapes the project root" in p for p in check(project(root, text), root))


def test_a_spec_with_no_scenarios_is_a_problem(tmp_path: Path) -> None:
    assert any("no scenarios" in p for p in check(project(tmp_path, "Feature: empty\n"), tmp_path))


def test_the_spec_file_must_exist_and_be_small(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        check(tmp_path / "missing.feature", tmp_path)
    big = tmp_path / "big.feature"
    big.write_text("Feature: x\n" + "# pad\n" * 40000)
    with pytest.raises(ValueError, match="byte limit"):
        check(big, tmp_path)


def test_scenario_is_a_plain_value() -> None:
    assert Scenario("s", (), (), False, ()) == Scenario("s", (), (), False, ())


def test_steps_may_contain_colons() -> None:
    feature = parse("Feature: x\n  @test(a.py)\n  Scenario: s\n    When the time is 10:30\n    Then output: ok\n")
    assert feature.problems == ()
    assert feature.scenarios[0].steps == (("When", "the time is 10:30"), ("Then", "output: ok"))


def test_free_text_under_feature_is_a_description() -> None:
    feature = parse("Feature: x\n  As a user I want y\n  @test(a.py)\n  Scenario: s\n    When a\n    Then b\n")
    assert feature.problems == ()
