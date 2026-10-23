import pytest

from task import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("2d", 172800), ("3h", 10800), ("4m", 240), ("5s", 5), ("0s", 0), ("1h30m", 5400), ("1d2h3m4s", 93784)],
)
def test_parses_each_unit_and_combinations(text: str, seconds: int) -> None:
    assert parse_duration(text) == seconds


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty duration"),
        ("5x", "unexpected text at 0"),
        ("x1h", "unexpected text at 0"),
        ("1h30", "unexpected text at 2"),
        ("30m1h", "units out of order or repeated"),
    ],
)
def test_rejects_invalid_text_with_a_clear_message(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        parse_duration(text)
