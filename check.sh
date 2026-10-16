#!/usr/bin/env bash
# One-line quality gate: lint, format, types, tests (100% branch coverage).
set -euo pipefail
cd "$(dirname "$0")"
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
