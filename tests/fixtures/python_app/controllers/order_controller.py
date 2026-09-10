"""REST controller exposing order operations."""

from tests.fixtures.python_app.services.order_service import OrderService


class OrderController:
    """Handles HTTP requests for orders."""

    def __init__(self) -> None:
        self.service = OrderService()

    def cancel_endpoint(self, order_id: str) -> dict:
        """Route handler for cancelling orders."""
        success = self.service.cancel_order(order_id)
        return {"cancelled": success}
