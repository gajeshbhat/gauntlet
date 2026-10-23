from task import split_amount


def test_even_split() -> None:
    assert split_amount(100, [1, 1]) == [50, 50]


def test_parts_add_up() -> None:
    assert sum(split_amount(100, [1, 1, 1])) == 100
