import pytest

from task import split_amount


@pytest.mark.parametrize(
    ("cents", "weights", "parts"),
    [
        (100, [1, 1, 1], [34, 33, 33]),
        (100, [1, 2], [33, 67]),
        (100, [2, 1], [67, 33]),
        (10, [3, 3, 4], [3, 3, 4]),
        (11, [3, 3, 4], [3, 3, 5]),
        (4, [2, 3], [2, 2]),
        (10**17 + 1, [1, 2], [33333333333333334, 66666666666666667]),
        (1, [1, 1, 1], [1, 0, 0]),
        (2, [1, 1, 1], [1, 1, 0]),
        (5, [1, 3], [1, 4]),
        (0, [0, 1], [0, 0]),
        (999, [7, 0, 3], [699, 0, 300]),
    ],
)
def test_split(cents: int, weights: list[int], parts: list[int]) -> None:
    assert split_amount(cents, weights) == parts
    assert sum(parts) == cents


@pytest.mark.parametrize(("cents", "weights"), [(-1, [1]), (1, []), (1, [1, -1]), (1, [0, 0]), (5, [2, -2]), (5, [3, -1])])
def test_invalid(cents: int, weights: list[int]) -> None:
    with pytest.raises(ValueError):
        split_amount(cents, weights)
