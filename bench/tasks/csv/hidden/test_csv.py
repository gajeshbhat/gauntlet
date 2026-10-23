import pytest

from task import split_line


@pytest.mark.parametrize(
    ("line", "fields"),
    [
        ("", [""]),
        ("a,,b", ["a", "", "b"]),
        ("a,b,", ["a", "b", ""]),
        (",,", ["", "", ""]),
        ('"x",', ["x", ""]),
        ('a,""', ["a", ""]),
        ('"""",b', ['"', "b"]),
        ('"a""b"', ['a"b']),
        ('"",""', ["", ""]),
        ('x,"y"', ["x", "y"]),
        ('"a,b,c"', ["a,b,c"]),
        ("  ", ["  "]),
    ],
)
def test_split(line: str, fields: list[str]) -> None:
    assert split_line(line) == fields


@pytest.mark.parametrize("line", ['"abc', 'a,"b""', '"a" ,b', '"a"x', 'a,"b"c'])
def test_invalid(line: str) -> None:
    with pytest.raises(ValueError):
        split_line(line)
