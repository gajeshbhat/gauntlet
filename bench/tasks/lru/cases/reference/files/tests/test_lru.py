import pytest

from task import LRUCache


def test_get_returns_the_value_or_the_default() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("b", 0) == 0


def test_evicts_the_least_recently_used() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert "a" not in cache
    assert ("b" in cache, "c" in cache) == (True, True)
    assert len(cache) == 2


def test_get_makes_a_key_recent() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert "a" in cache and "b" not in cache


def test_put_updates_a_value_without_growing() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("a", 9)
    assert cache.get("a") == 9
    assert len(cache) == 1


def test_capacity_must_be_positive() -> None:
    with pytest.raises(ValueError, match="^capacity must be at least 1$"):
        LRUCache(0)


def test_capacity_one_holds_one_key() -> None:
    cache = LRUCache(1)
    cache.put("a", 1)
    assert cache.get("a") == 1
