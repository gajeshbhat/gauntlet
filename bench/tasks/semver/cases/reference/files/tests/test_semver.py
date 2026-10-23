import pytest

from task import compare


@pytest.mark.parametrize(
    ("low", "high"),
    [
        ("1.0.0", "2.0.0"),
        ("1.0.0", "1.1.0"),
        ("1.0.0", "1.0.1"),
        ("1.9.0", "1.10.0"),
        ("1.0.0-alpha", "1.0.0"),
        ("1.0.0-alpha", "1.0.0-alpha.1"),
        ("1.0.0-alpha.1", "1.0.0-alpha.beta"),
        ("1.0.0-beta", "1.0.0-beta.2"),
        ("1.0.0-rc.1", "1.0.0-rc.2"),
        ("1.0.0-a.b", "1.0.0-a-b"),
    ],
)
def test_orders_versions(low: str, high: str) -> None:
    assert compare(low, high) == -1
    assert compare(high, low) == 1


@pytest.mark.parametrize(("a", "b"), [("1.2.3", "1.2.3"), ("1.0.0-alpha.1", "1.0.0-alpha.1"), ("1.0.0+a", "1.0.0+b")])
def test_equal_versions(a: str, b: str) -> None:
    assert compare(a, b) == 0


@pytest.mark.parametrize("bad", ["1.2", "01.2.3", "1.2.3-", "v1.2.3"])
def test_invalid_versions_are_named(bad: str) -> None:
    with pytest.raises(ValueError, match=f"^invalid version: '{bad}'$"):
        compare(bad, "1.0.0")
