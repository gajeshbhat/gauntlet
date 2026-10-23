from task import slugify


def test_basic() -> None:
    assert slugify("Hello World") == "hello-world"


def test_punctuation() -> None:
    assert slugify("Hello, World!") == "hello-world"


def test_max_length() -> None:
    assert len(slugify("hello world", max_length=5)) <= 5
