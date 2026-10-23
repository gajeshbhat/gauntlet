# Task: an LRU cache

Implement `task.LRUCache` in `src/task/__init__.py`, and write tests in `tests/`.

- `LRUCache(capacity: int)`; `capacity < 1` raises `ValueError("capacity must be at least 1")`.
- `get(key, default=None)` returns the value or `default`. A hit makes the key the most recently used.
- `put(key, value)` stores the value and makes the key the most recently used. If that puts the cache over
  capacity, the least recently used key is evicted.
- `len(cache)` is the number of keys; `key in cache` tells whether a key is cached and does **not** change recency.
