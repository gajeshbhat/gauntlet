from collections import OrderedDict
from typing import Any


class LRUCache:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._items: OrderedDict[Any, Any] = OrderedDict()

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._items:
            return default
        self._items.move_to_end(key)
        return self._items[key]

    def put(self, key: Any, value: Any) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        if len(self._items) > self.capacity:
            del self._items[next(iter(self._items))]

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: object) -> bool:
        return key in self._items
