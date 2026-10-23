import pytest

from task import slugify


@pytest.mark.parametrize(
    ("text", "max_length", "slug"),
    [
        ("Hello World", None, "hello-world"),
        ("Crème Brûlée", None, "creme-brulee"),
        ("naïve café", None, "naive-cafe"),
        ("日本 text", None, "text"),
        ("--a--b--", None, "a-b"),
        ("ABC", None, "abc"),
        ("snake_case name", None, "snake-case-name"),
        ("  hello", 3, "hel"),
        ("hello world", 6, "hello"),
        ("hello world", 1, "h"),
        ("a-b", 2, "a"),
        ("hello", 50, "hello"),
        ("", 3, ""),
    ],
)
def test_slugify(text: str, max_length: int | None, slug: str) -> None:
    assert slugify(text, max_length) == slug


@pytest.mark.parametrize("bad", [0, -1])
def test_bad_max_length(bad: int) -> None:
    with pytest.raises(ValueError):
        slugify("x", bad)
