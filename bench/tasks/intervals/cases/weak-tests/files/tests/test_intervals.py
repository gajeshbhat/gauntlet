import pytest

from task import merge_intervals


def test_merges_overlap() -> None:
    assert merge_intervals([(1, 3), (2, 5)]) == [(1, 5)]


def test_keeps_separate_intervals() -> None:
    assert merge_intervals([(1, 2), (5, 6)]) == [(1, 2), (5, 6)]


def test_bad_interval() -> None:
    with pytest.raises(ValueError):
        merge_intervals([(3, 1)])
