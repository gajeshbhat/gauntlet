import pytest

from task import Page, paginate


@pytest.mark.parametrize(
    ("total", "page", "per_page", "expected"),
    [
        (25, 1, 10, Page(0, 10, 3, False, True)),
        (25, 2, 10, Page(10, 20, 3, True, True)),
        (25, 3, 10, Page(20, 25, 3, True, False)),
        (20, 2, 10, Page(10, 20, 2, True, False)),
        (0, 1, 10, Page(0, 0, 1, False, False)),
        (1, 1, 1, Page(0, 1, 1, False, False)),
    ],
)
def test_pages(total: int, page: int, per_page: int, expected: Page) -> None:
    assert paginate(total, page, per_page) == expected


@pytest.mark.parametrize(
    ("total", "page", "per_page", "message"),
    [
        (-1, 1, 10, "total -1 is negative"),
        (10, 1, 0, "per_page 0 is below 1"),
        (25, 4, 10, "page 4 is out of range 1-3"),
        (25, 0, 10, "page 0 is out of range 1-3"),
    ],
)
def test_bad_arguments_are_named(total: int, page: int, per_page: int, message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        paginate(total, page, per_page)
