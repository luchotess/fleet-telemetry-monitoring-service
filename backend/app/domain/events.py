from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    aggregate_id: str | None
    payload: dict[str, Any]
    occurred_at: datetime


def build_event(
    event_type: str,
    aggregate_id: str | None,
    payload: dict[str, Any] | None = None,
) -> DomainEvent:
    return DomainEvent(
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        occurred_at=datetime.now(timezone.utc),
    )


class DomainEventPublisher:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[DomainEvent], None]] = []

    def subscribe(self, handler: Callable[[DomainEvent], None]) -> None:
        self._subscribers.append(handler)

    def clear(self) -> None:
        self._subscribers.clear()

    def publish_many(self, events: list[DomainEvent]) -> None:
        for event in events:
            for handler in list(self._subscribers):
                handler(event)


publisher = DomainEventPublisher()
