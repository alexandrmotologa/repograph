"""Circular dependency test node Beta."""

from tests.fixtures.python_app.cycles.alpha import step_alpha


def step_beta() -> str:
    # Mutual circular call
    if False:
        step_alpha()
    return "done"
