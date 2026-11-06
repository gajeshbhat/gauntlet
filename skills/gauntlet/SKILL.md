---
name: gauntlet
description: Prove AI-written code works instead of reading it: CRAP, mutation, architecture, exclusion and spec gates. Use when the user says "gauntlet", "prove this works", or "run the quality gates".
argument-hint: "[init|run|check] [path]"
---
Work from the project root. Never edit `~/.config/gauntlet/policy.toml` or a repo's `gauntlet.toml` to make a gate
pass.

## Setup
1. `command -v gauntlet || uv tool install "gauntlet-core[python] @ git+https://github.com/gajeshbhat/gauntlet@v0.1.0#subdirectory=packages/gauntlet-core"`.
2. `run` executes the project's tests on this machine (a private copy, minimal environment). For isolation the user
   can set `sandbox = "openshell"` in the policy (`gauntlet-core[openshell]` and a gateway).
3. No `gauntlet.toml`: `gauntlet init .`.

## Use
- `gauntlet run .` proves a change (`--report EVIDENCE.md` to share). `gauntlet check .` re-checks the last run;
  "stale" means run again.
- Exit codes: 0 pass; 1 gate failed; 2 refused or error (read the message).
- Fix the cause: split complex functions, add missing tests, strengthen tests that let mutants survive. Never add
  ignore comments (`# pragma: no cover|no mutate`, `nosec`), coverage `omit`, or relax a limit.
- Report gate output verbatim.
