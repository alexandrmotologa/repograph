"""Domain model for order aggregate root."""


class Order:
    """Represents a customer order with lifecycle states."""

    def __init__(self, order_id: str, total: float) -> None:
        self.order_id = order_id
        self.total = total
        self.status = "CREATED"

    def cancel(self) -> None:
        """Cancel the order and emit domain events."""
        if self.status == "COMPLETED":
            raise ValueError("Cannot cancel completed order")
        self.status = "CANCELLED"
        self.record_event("OrderCancelled")

    def record_event(self, event_name: str) -> None:
        """Append domain event to outbox."""
        print(f"Event recorded: {event_name}")
