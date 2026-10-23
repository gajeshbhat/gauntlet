import pytest

from task import merge_intervals


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ([], []),
        ([(1, 3), (3, 5)], [(1, 5)]),
        ([(1, 2), (3, 4)], [(1, 2), (3, 4)]),
        ([(1, 2), (2, 2)], [(1, 2)]),
        ([(-5, -1), (-2, 0)], [(-5, 0)]),
        ([(1, 10), (2, 3), (4, 12), (20, 21)], [(1, 12), (20, 21)]),
        ([(7, 8), (1, 2), (2, 3)], [(1, 3), (7, 8)]),
    ],
)
def test_merge(given: list[tuple[int, int]], expected: list[tuple[int, int]]) -> None:
    assert merge_intervals(given) == expected


@pytest.mark.parametrize("given", [[(3, 1)], [(1, 5), (3, 2)], [(0, 1), (9, 8)]])
def test_invalid(given: list[tuple[int, int]]) -> None:
    with pytest.raises(ValueError):
        merge_intervals(given)


def test_input_is_not_changed() -> None:
    given = [(5, 6), (1, 2)]
    merge_intervals(given)
    assert given == [(5, 6), (1, 2)]
