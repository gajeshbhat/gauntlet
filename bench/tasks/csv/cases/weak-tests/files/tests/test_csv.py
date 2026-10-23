from task import split_line


def test_simple() -> None:
    assert split_line("a,b,c") == ["a", "b", "c"]


def test_quoted_comma() -> None:
    assert split_line('"a,b",c') == ["a,b", "c"]
