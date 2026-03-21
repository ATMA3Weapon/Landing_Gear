from __future__ import annotations

from typing import Any, Protocol


class Repository(Protocol):
    async def health(self) -> dict[str, Any]: ...


class MemoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    async def health(self) -> dict[str, Any]:
        return {'ok': True, 'backend': 'memory', 'keys': sorted(self.items.keys())}


class KeyValueRepository(MemoryRepository):
    async def get(self, key: str) -> Any:
        return self.items.get(key)

    async def set(self, key: str, value: Any) -> None:
        self.items[key] = value
