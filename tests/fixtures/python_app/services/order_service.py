"""Application service orchestrating order workflows."""

from tests.fixtures.python_app.infra.outbox import OutboxRelay
from tests.fixtures.python_app.models.order import Order


class OrderService:
    """Orchestrates order operations and relays events."""

    def __init__(self) -> None:
        self.relay = OutboxRelay()

    def cancel_order(self, order_id: str) -> bool:
        """Find order, perform cancellation, and trigger outbox relay."""
        order = Order(order_id, 100.0)
        order.cancel()
        self.relay.dispatch("OrderCancelled")
        return True
