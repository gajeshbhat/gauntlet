from task import LRUCache


def test_put_and_get() -> None:
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1


def test_eviction() -> None:
    cache = LRUCache(1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") is None
