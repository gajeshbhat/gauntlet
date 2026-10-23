import pytest

from task import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("1h30m", 5400), ("45s", 45), ("2d", 172800), ("1d2h3m4s", 93784), ("0s", 0), ("90m", 5400), ("1d1s", 86401)],
)
def test_valid(text: str, seconds: int) -> None:
    assert parse_duration(text) == seconds


@pytest.mark.parametrize(
    "text", ["", "h", "5", "1x", "1H", "1h 30m", " 1h", "1h ", "30m1h", "1h1h", "1s1m", "1h30", "-1h", "1.5h", "1hm"]
)
def test_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(text)
