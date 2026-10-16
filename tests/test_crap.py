import pytest

from gauntlet.crap import crap_score


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
