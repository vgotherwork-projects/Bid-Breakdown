"""Simple thread-safe in-memory store.

Swap this out for a real database (SQLAlchemy, etc.) when you outgrow it.
"""
from datetime import datetime, timezone
from threading import Lock

from .schemas import ItemCreate, ItemUpdate


class ItemStore:
    def __init__(self) -> None:
        self._items: dict[int, dict] = {}
        self._next_id = 1
        self._lock = Lock()

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._items.values())

    def get(self, item_id: int) -> dict | None:
        with self._lock:
            return self._items.get(item_id)

    def create(self, payload: ItemCreate) -> dict:
        with self._lock:
            item = {
                "id": self._next_id,
                "created_at": datetime.now(timezone.utc),
                **payload.model_dump(),
            }
            self._items[self._next_id] = item
            self._next_id += 1
            return item

    def update(self, item_id: int, payload: ItemUpdate) -> dict | None:
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                return None
            changes = payload.model_dump(exclude_unset=True)
            item.update(changes)
            return item

    def delete(self, item_id: int) -> bool:
        with self._lock:
            return self._items.pop(item_id, None) is not None


store = ItemStore()
