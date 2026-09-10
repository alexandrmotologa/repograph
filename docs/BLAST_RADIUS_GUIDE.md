# Blast Radius & Impact Analysis Guide

This guide explains how RepoGraph computes the blast radius of code changes, categorizes impact severity, and helps prevent regressions during refactoring.

## What is blast radius?

When modifying or deprecating a core function or method, changes can cascade across modules, handlers, controllers, and tests.

Blast radius analysis computes:
1. **Upstream impact (Who breaks if I change?)**: Traverses incoming directed edges (`CALLS` and `IMPORTS` in reverse) to find all consumers that rely on the symbol.
2. **Downstream impact (What side effects do I trigger?)**: Traverses outgoing directed edges (`CALLS`) to find all internal methods, external APIs, and side effects executed downstream.

## Severity classification

RepoGraph assigns an impact category to each affected node:

- **CRITICAL**: Public HTTP route handlers, REST endpoints, CLI commands, and framework controllers. Breaking changes to these symbols affect external consumers and user requests.
- **HIGH**: Domain aggregate roots, service layer boundaries, and shared database models.
- **MEDIUM**: Private helper methods and internal utilities.
- **TEST**: Test functions, test suites, and assertions verifying the affected call paths.

## Blast radius score formula

RepoGraph quantifies refactoring risk into a score from 0.0 to 100.0:

$$\text{Raw Score} = (N_u \times 4.0) + (N_d \times 1.5) + (N_e \times 20.0) + (N_f \times 5.0)$$

Where:
- $N_u$: Number of upstream callers
- $N_d$: Number of downstream dependencies
- $N_e$: Number of public entrypoints (APIs, CLI commands) affected
- $N_f$: Number of distinct files touched

### Test presence factor

If affected paths have associated test cases ($N_t > 0$), the raw score is discounted using:

$$\text{Factor} = \max(0.60, 1.0 - (N_t \times 0.08))$$

If no test cases exist ($N_t = 0$), a 25% risk penalty is applied to reflect unverified refactoring risk. The score is clamped between 0.0 and 100.0.

| Score range | Risk level | Recommended action |
|-------------|------------|--------------------|
| 0 to 30     | Low        | Safe to refactor with standard unit testing. |
| 31 to 70    | Medium     | Review intermediate callers and verify integration tests. |
| 71 to 100   | Critical   | Public API or core domain change. Requires comprehensive regression testing and deprecation planning. |

## CI/CD integration example

You can use RepoGraph in GitHub Actions pull request checks to post an impact report comment:

```yaml
name: Blast Radius Check

on:
  pull_request:
    branches: [ main ]

jobs:
  impact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Calculate blast radius
        run: |
          uv run repograph blast-radius "Order.cancel" --dir .
```
