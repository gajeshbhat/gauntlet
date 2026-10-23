from task import paginate


def test_first_page() -> None:
    page = paginate(25, 1, 10)
    assert page.start == 0
    assert page.pages == 3


def test_last_page() -> None:
    assert paginate(25, 3, 10).has_next is False
