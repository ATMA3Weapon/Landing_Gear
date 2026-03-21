from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class HelloRepository:
    service_name: str
    request_count: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def greet(self, name: str) -> dict[str, Any]:
        self.request_count += 1
        event = {
            'name': name,
            'message': f'Hello, {name}!',
            'request_number': self.request_count,
            'at': datetime.now(timezone.utc).isoformat(),
        }
        self.history.append(event)
        if len(self.history) > 25:
            del self.history[:-25]
        return event

    def summary(self) -> dict[str, Any]:
        return {
            'service_name': self.service_name,
            'request_count': self.request_count,
            'recent_names': [item['name'] for item in self.history[-5:]],
        }

    async def health(self) -> dict[str, Any]:
        return {
            'ok': True,
            'backend': 'memory',
            'request_count': self.request_count,
            'history_size': len(self.history),
        }
