import pytest

from task import compare

ORDER = [
    "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11",
    "1.0.0-rc.1", "1.0.0", "1.0.1", "1.2.0", "1.10.0", "2.0.0",
]


@pytest.mark.parametrize("i", range(len(ORDER) - 1))
def test_precedence(i: int) -> None:
    assert compare(ORDER[i], ORDER[i + 1]) == -1
    assert compare(ORDER[i + 1], ORDER[i]) == 1


@pytest.mark.parametrize(
    ("a", "b"), [("1.0.0+build.1", "1.0.0+build.2"), ("1.0.0-rc.1+x", "1.0.0-rc.1"), ("0.0.0", "0.0.0")]
)
def test_equal(a: str, b: str) -> None:
    assert compare(a, b) == 0


@pytest.mark.parametrize("bad", ["1", "1.2", "1.2.3.4", "01.0.0", "1.02.0", "1.0.0-", "1.0.0+", "a.b.c", ""])
def test_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        compare(bad, "1.0.0")
    with pytest.raises(ValueError):
        compare("1.0.0", bad)
