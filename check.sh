#!/usr/bin/env bash
# One-line quality gate: lint, format, types, tests (100% branch coverage).
set -euo pipefail
cd "$(dirname "$0")"
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
uv run pytest -q --no-cov bench/test_harness.py
uv run gauntlet stamp . --artifacts .
uv run gauntlet check . --artifacts . --only src/gauntlet/ --policy policy.ci.toml
uv run gauntlet spec . --feature specs/languages.feature --policy policy.ci.toml
