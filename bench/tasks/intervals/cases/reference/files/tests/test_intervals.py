import pytest

from task import merge_intervals


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ([], []),
        ([(1, 3)], [(1, 3)]),
        ([(2, 2)], [(2, 2)]),
        ([(1, 3), (2, 5)], [(1, 5)]),
        ([(1, 3), (3, 5)], [(1, 5)]),
        ([(1, 10), (2, 3)], [(1, 10)]),
        ([(5, 6), (1, 2)], [(1, 2), (5, 6)]),
        ([(1, 2), (5, 6), (4, 7)], [(1, 2), (4, 7)]),
    ],
)
def test_merges_overlapping_and_touching_intervals(given: list[tuple[int, int]], expected: list[tuple[int, int]]) -> None:
    assert merge_intervals(given) == expected


def test_start_after_end_is_named() -> None:
    with pytest.raises(ValueError, match=r"^start after end: \(3, 1\)$"):
        merge_intervals([(3, 1)])
