from task import wrap


def test_short_text_fits() -> None:
    assert wrap("hello world", 20) == ["hello world"]


def test_wraps_long_text() -> None:
    assert len(wrap("the quick brown fox", 10)) > 1
