#!/usr/bin/env bash
# Run every benchmark case (needs Docker), then write bench/RESULTS.md. Pass --task NAME to run only some tasks.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python bench/harness.py run "$@"
uv run python bench/harness.py report "$@"
