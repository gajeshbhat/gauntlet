import pytest

from gauntlet_python.mutmut import check

RESULTS = """
    pkg.x_a__mutmut_1: killed
    pkg.x_a__mutmut_2: survived
    pkg.x_b__mutmut_1: timeout
    pkg.x_b__mutmut_2: skipped
    pkg.x_c__mutmut_1: no tests
"""


def test_score_counts_killed_and_timeout_and_ignores_skipped() -> None:
    result = check(RESULTS)
    assert (result.caught, result.total) == (2, 4)
    assert result.survivors == ["pkg.x_a__mutmut_2: survived", "pkg.x_c__mutmut_1: no tests"]


def test_score_of_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match=r"^no mutants found; is \[tool.mutmut\] configured in the target repo\?$"):
        check("")


def test_check_turns_results_into_a_mutation_result() -> None:
    result = check(RESULTS)
    assert result.pct == 50.0
    assert (result.caught, result.total) == (2, 4)
    assert result.survivors == ["pkg.x_a__mutmut_2: survived", "pkg.x_c__mutmut_1: no tests"]


def test_segfaults_count_as_caught() -> None:
    assert check("a: segfault\nb: survived\n").pct == 50.0


def test_mutants_that_were_all_never_checked_mean_mutmut_did_not_run() -> None:
    with pytest.raises(ValueError, match=r"mutmut checked no mutant: its tests never ran.*mutmut run"):
        check("pkg.x_a__mutmut_1: not checked\npkg.x_a__mutmut_2: not checked\n")


def test_a_few_unchecked_mutants_among_checked_ones_are_survivors_not_an_error() -> None:
    assert check("pkg.x_a__mutmut_1: killed\npkg.x_a__mutmut_2: not checked\n").pct == 50.0
