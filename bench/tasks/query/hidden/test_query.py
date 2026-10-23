import pytest

from task import parse_query


@pytest.mark.parametrize(
    ("query", "parsed"),
    [
        ("", {}),
        ("&&", {}),
        ("a=1&a=2&b", {"a": ["1", "2"], "b": [""]}),
        ("a=", {"a": [""]}),
        ("=v", {"": ["v"]}),
        ("q=%2B+%2b", {"q": ["+ +"]}),
        ("q=%25", {"q": ["%"]}),
        ("q=x%26y%3Dz&r=1", {"q": ["x&y=z"], "r": ["1"]}),
        ("k%3Dey=v", {"k=ey": ["v"]}),
        ("caf%C3%A9=1", {"café": ["1"]}),
        ("q=a=b=c", {"q": ["a=b=c"]}),
    ],
)
def test_parse(query: str, parsed: dict[str, list[str]]) -> None:
    assert parse_query(query) == parsed


@pytest.mark.parametrize("query", ["q=%", "q=%4", "q=%g1", "%zz=1", "a=1&b=%x"])
def test_bad_escape(query: str) -> None:
    with pytest.raises(ValueError):
        parse_query(query)


@pytest.mark.parametrize(("query", "position"), [("a&&b=%x", 5), ("&q=%", 3), ("x=1&%q=", 4)])
def test_bad_escape_position(query: str, position: int) -> None:
    with pytest.raises(ValueError, match=f"at {position}$"):
        parse_query(query)
