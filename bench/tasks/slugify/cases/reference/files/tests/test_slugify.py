import pytest

from task import slugify


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Hello World", "hello-world"),
        ("  Hello,   World!  ", "hello-world"),
        ("Crème Brûlée", "creme-brulee"),
        ("a.b c", "a-b-c"),
        ("Version 2 0", "version-2-0"),
        ("---", ""),
        ("", ""),
    ],
)
def test_slugs(text: str, slug: str) -> None:
    assert slugify(text) == slug


def test_max_length_cuts_and_drops_a_trailing_dash() -> None:
    assert slugify("hello world", max_length=6) == "hello"
    assert slugify("hello", max_length=1) == "h"
    assert slugify("hello world", max_length=7) == "hello-w"
    assert slugify("hello", max_length=5) == "hello"


def test_max_length_must_be_positive() -> None:
    with pytest.raises(ValueError, match="^max_length must be at least 1$"):
        slugify("x", max_length=0)
