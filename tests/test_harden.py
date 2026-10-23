import pytest

from gauntlet.harden import check

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
