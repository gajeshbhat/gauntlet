import pytest

from task import wrap


@pytest.mark.parametrize(
    ("text", "width", "lines"),
    [
        ("", 3, []),
        ("one two three", 7, ["one two", "three"]),
        ("one two three", 8, ["one two", "three"]),
        ("abcdefgh", 4, ["abcd", "efgh"]),
        ("abcdefg x", 3, ["abc", "def", "g x"]),
        ("abcdefgh xy", 3, ["abc", "def", "gh", "xy"]),
        ("a\tb\nc", 1, ["a", "b", "c"]),
        ("x " * 3, 3, ["x x", "x"]),
    ],
)
def test_wrap(text: str, width: int, lines: list[str]) -> None:
    assert wrap(text, width) == lines


@pytest.mark.parametrize("width", [0, -3])
def test_bad_width(width: int) -> None:
    with pytest.raises(ValueError):
        wrap("x", width)
