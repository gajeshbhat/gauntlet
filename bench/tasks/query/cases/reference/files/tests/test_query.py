import pytest

from task import parse_query


@pytest.mark.parametrize(
    ("query", "parsed"),
    [
        ("", {}),
        ("a=1", {"a": ["1"]}),
        ("a=1&b=2", {"a": ["1"], "b": ["2"]}),
        ("a=1&a=2", {"a": ["1", "2"]}),
        ("a=1&&b=2", {"a": ["1"], "b": ["2"]}),
        ("flag", {"flag": [""]}),
        ("q=a+b", {"q": ["a b"]}),
        ("q=%41%62", {"q": ["Ab"]}),
        ("q=%e2%82%ac", {"q": ["€"]}),
        ("q=x%26y%3Dz", {"q": ["x&y=z"]}),
        ("q=a=b", {"q": ["a=b"]}),
        ("my+key=1", {"my key": ["1"]}),
    ],
)
def test_parses(query: str, parsed: dict[str, list[str]]) -> None:
    assert parse_query(query) == parsed


@pytest.mark.parametrize(("query", "message"), [("q=%zz", "bad escape at 2"), ("a=1&b=%4", "bad escape at 6")])
def test_bad_escape_names_its_position(query: str, message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        parse_query(query)
