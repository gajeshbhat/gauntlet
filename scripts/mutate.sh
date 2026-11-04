#!/usr/bin/env bash
# Mutation-test each package on its own and merge the results into ./mutmut-results.txt for `gauntlet harden`.
# mutmut 3.x only understands a top-level src/ layout, so it cannot mutate the monorepo from the root: it runs one
# package at a time (each has its own tests/) and the module names stay unique across packages.
set -euo pipefail
cd "$(dirname "$0")/.."
root=$PWD
: > mutmut-results.txt
for pkg in packages/gauntlet-*/; do
    (
        cd "$pkg"
        rm -rf mutants
        run=(uv run --isolated --project . --group test --with mutmut==3.8.1 --with pytest-cov==7.1.0 mutmut)
        "${run[@]}" run > /dev/null || true # mutants that survive make mutmut exit non-zero; `harden` judges the score
        "${run[@]}" results --all true >> "$root/mutmut-results.txt"
        rm -rf mutants
    )
done
