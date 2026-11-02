#!/usr/bin/env bash
# One-line quality gate: lint, format, types, tests (100% branch coverage).
set -euo pipefail
cd "$(dirname "$0")"
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
uv run gauntlet stamp . --artifacts .
uv run gauntlet check . --artifacts . --only packages/gauntlet-core/src/ --only packages/gauntlet-sandbox/src/ --only packages/gauntlet-python/src/ --policy policy.ci.toml
uv run gauntlet spec . --feature specs/languages.feature --policy policy.ci.toml
uv run --isolated --package gauntlet-sandbox --group test pytest --no-cov packages/gauntlet-sandbox/tests -q
uv run --isolated --package gauntlet-core --group test pytest --no-cov packages/gauntlet-core/tests -q
uv run --isolated --package gauntlet-python --group test pytest --no-cov packages/gauntlet-python/tests -q
