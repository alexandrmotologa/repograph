"""Test suite exercising OrderService."""

from tests.fixtures.python_app.services.order_service import OrderService


def test_order_cancellation():
    service = OrderService()
    result = service.cancel_order("ORD-123")
    assert result is True
