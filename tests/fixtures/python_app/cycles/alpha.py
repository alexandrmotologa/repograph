"""Circular dependency test node Alpha."""

from tests.fixtures.python_app.cycles.beta import step_beta


def step_alpha() -> str:
    return step_beta()
