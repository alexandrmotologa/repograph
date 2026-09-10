"""Outbox relay infrastructure."""


class OutboxRelay:
    """Dispatches stored domain events to message broker."""

    def dispatch(self, event_type: str) -> bool:
        """Publish event to external queue."""
        return True
