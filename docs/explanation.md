# Explanation

## Why a gauntlet

An agent writes code faster than anyone can review it. gauntlet replaces review with evidence.

## Fail closed

A gate that checked nothing never passes: empty coverage, an `--only` that matches nothing, or no mutants in scope
exit 2. A file missing from coverage counts as 0%; a mutant no test ran counts as survived.

## Why CRAP

CRAP is complexity² × (1 − coverage)³ + complexity, so the default limit of 8 also caps complexity. Tests can run code
without checking it, so mutation testing backs up coverage.

## Rules live outside the repository

An agent that can edit the repo can edit its config, so your limits live in a policy file outside it. The repo's
`gauntlet.toml` may only tighten them.

## Results are bound to the source

`stamp` hashes the artifacts with the source. Gates refuse artifacts that don't match, so yesterday's coverage can't
pass today's code.

## Code runs only in the sandbox

Tests, mutation tools and agents run in a sandbox on a private copy of the repo; gates only read the results. The
sandbox protects your machine, not the numbers. See [SECURITY.md](../SECURITY.md).

## The agent loop

You approve the spec; agents implement it and return a patch. Edits to control files (CI, `gauntlet.toml`, build
config) are flagged, since they could weaken the checks.
