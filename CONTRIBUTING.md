# Contributing to RepoGraph

Thank you for your interest in improving RepoGraph. This guide outlines development setup, testing standards, and contribution guidelines.

## Development environment

RepoGraph uses Python 3.12+ and `uv` for fast dependency management.

1. Fork the repository and clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/repograph.git
   cd repograph
   ```

2. Create virtual environment and install development dependencies:
   ```bash
   uv venv
   uv pip install -e ".[dev]"
   ```

## Code style and standards

RepoGraph enforces strict code quality using Ruff:

- Target Python version: 3.12
- Line length: 100 characters
- To check formatting and lint rules:
  ```bash
  uv run ruff check .
  uv run ruff format --check .
  ```
- To auto-format and fix lint warnings:
  ```bash
  uv run ruff check --fix .
  uv run ruff format .
  ```

## Writing tests

All new features, parser additions, and bug fixes must include unit or integration tests:

1. Add tests in `tests/unit/` or `tests/integration/`.
2. Add sample code fixtures under `tests/fixtures/` if adding a new language or grammar.
3. Run test suite:
   ```bash
   uv run pytest -v --cov=repograph --cov-report=term-missing
   ```

Make sure all tests pass before submitting a pull request.

## Submitting changes

1. Create a descriptive branch:
   ```bash
   git checkout -b feat/go-language-parser
   ```
2. Commit changes using clear commit messages (e.g. `feat: add tree-sitter parser for Go source files`).
3. Push to your fork and open a pull request against `main`.
4. Ensure CI tests pass across Linux, Windows, and macOS runners.
