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

## Project code runs on a private copy

Tests and mutation tools run on a throwaway copy of the repo; gates only read the results. That copy is on your machine
unless you choose an OpenShell sandbox, which also keeps the code away from your files and network. A sandbox
protects your machine, not the numbers. See [SECURITY.md](../SECURITY.md).
