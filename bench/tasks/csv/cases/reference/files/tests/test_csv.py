import pytest

from task import split_line


@pytest.mark.parametrize(
    ("line", "fields"),
    [
        ("", [""]),
        ("a", ["a"]),
        ("a,b,c", ["a", "b", "c"]),
        ("a,", ["a", ""]),
        (",", ["", ""]),
        (" a , b ", [" a ", " b "]),
        ('"a,b",c', ["a,b", "c"]),
        ('"say ""hi""",x', ['say "hi"', "x"]),
        ('""', [""]),
        ('a"b,c', ['a"b', "c"]),
    ],
)
def test_splits(line: str, fields: list[str]) -> None:
    assert split_line(line) == fields


@pytest.mark.parametrize(("line", "message"), [('a,"bc', "unclosed quote at 2"), ('"a"b', "text after closing quote at 3")])
def test_bad_quotes_are_named(line: str, message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        split_line(line)
