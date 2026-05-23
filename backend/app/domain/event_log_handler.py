from collections.abc import Callable

from sqlalchemy.orm import Session

from app.db.models import DomainEventLog
from app.domain.events import DomainEvent


def make_domain_event_log_handler(
    session_factory: Callable[[], Session],
) -> Callable[[DomainEvent], None]:
    def handler(event: DomainEvent) -> None:
        with session_factory() as db:
            db.add(
                DomainEventLog(
                    event_type=event.event_type,
                    aggregate_id=event.aggregate_id,
                    payload={
                        **event.payload,
                        "occurred_at": event.occurred_at.isoformat(),
                    },
                )
            )
            db.commit()

    return handler
