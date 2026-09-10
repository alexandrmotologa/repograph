"""Unused utility functions demonstrating dead code detection."""


def orphan_tax_calculator(amount: float) -> float:
    """Calculates tax but is never imported or called anywhere in the repository."""
    return amount * 0.20


def unused_legacy_serializer(data: dict) -> str:
    """Legacy serializer deprecated and uncalled."""
    return str(data)
