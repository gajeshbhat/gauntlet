import pytest

from task import wrap


@pytest.mark.parametrize(
    ("text", "width", "lines"),
    [
        ("", 5, []),
        ("   ", 5, []),
        ("hello", 5, ["hello"]),
        ("hello world", 11, ["hello world"]),
        ("hello world", 10, ["hello", "world"]),
        ("a b c d", 3, ["a b", "c d"]),
        ("a  b\n c", 5, ["a b c"]),
        ("abcdefgh", 3, ["abc", "def", "gh"]),
        ("hi abcdefgh", 3, ["hi", "abc", "def", "gh"]),
        ("a b", 1, ["a", "b"]),
    ],
)
def test_wraps(text: str, width: int, lines: list[str]) -> None:
    assert wrap(text, width) == lines


def test_width_must_be_positive() -> None:
    with pytest.raises(ValueError, match="^width must be at least 1$"):
        wrap("x", 0)
