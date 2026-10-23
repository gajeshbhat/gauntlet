import pytest

from task import Page, paginate


@pytest.mark.parametrize(
    ("total", "page", "per_page", "expected"),
    [
        (25, 1, 10, Page(0, 10, 3, False, True)),
        (25, 3, 10, Page(20, 25, 3, True, False)),
        (30, 3, 10, Page(20, 30, 3, True, False)),
        (31, 4, 10, Page(30, 31, 4, True, False)),
        (0, 1, 5, Page(0, 0, 1, False, False)),
        (5, 1, 100, Page(0, 5, 1, False, False)),
        (7, 7, 1, Page(6, 7, 7, True, False)),
    ],
)
def test_paginate(total: int, page: int, per_page: int, expected: Page) -> None:
    assert paginate(total, page, per_page) == expected


@pytest.mark.parametrize(
    ("total", "page", "per_page"), [(-1, 1, 10), (10, 1, 0), (10, 1, -5), (25, 4, 10), (25, 0, 10), (0, 2, 10), (10, -1, 5)]
)
def test_invalid(total: int, page: int, per_page: int) -> None:
    with pytest.raises(ValueError):
        paginate(total, page, per_page)
