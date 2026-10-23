from task import parse_query


def test_simple() -> None:
    assert parse_query("a=1&b=2") == {"a": ["1"], "b": ["2"]}


def test_plus_is_space() -> None:
    assert parse_query("q=a+b")["q"] == ["a b"]
