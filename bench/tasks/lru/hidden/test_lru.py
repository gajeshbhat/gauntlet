import pytest

from task import LRUCache


def test_update_makes_a_key_recent() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 3)
    cache.put("c", 4)
    assert cache.get("a") == 3 and "b" not in cache


def test_contains_does_not_change_recency() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert "a" in cache
    cache.put("c", 3)
    assert "a" not in cache


def test_falsy_values_are_cached() -> None:
    cache = LRUCache(2)
    cache.put("zero", 0)
    cache.put("none", None)
    assert cache.get("zero", "missing") == 0
    assert cache.get("none", "missing") is None
    assert len(cache) == 2


def test_capacity_one() -> None:
    cache = LRUCache(1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert (len(cache), cache.get("b"), "a" in cache) == (1, 2, False)


def test_miss_does_not_evict() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("x")
    cache.put("c", 3)
    assert "a" not in cache and "b" in cache


@pytest.mark.parametrize("bad", [0, -1])
def test_bad_capacity(bad: int) -> None:
    with pytest.raises(ValueError):
        LRUCache(bad)
