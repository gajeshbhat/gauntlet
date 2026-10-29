---
name: gauntlet
description: Prove AI-written code works instead of reading it: CRAP, mutation, architecture, exclusion and spec gates in a sandbox, plus a spec-first agent loop that ends in a patch. Use when the user says "gauntlet", "prove this works", "run the quality gates", or wants a spec-first agent workflow.
argument-hint: "[init|run|check|loop] [path]"
---
Work from the project root. Never edit `~/.config/gauntlet/policy.toml` or a repo's `gauntlet.toml` to make a gate
pass.

## Setup
1. `command -v gauntlet || uv tool install git+https://github.com/gajeshbhat/gauntlet`.
2. `run` and `loop` need Workshop or Docker/Podman (`command -v workshop docker`). Tell the user what to install;
   never run `sudo`. With Docker, `loop` also needs `docker_image_agent` in the policy.
3. No `gauntlet.toml`: `gauntlet init .`.

## Use
- `gauntlet run .` proves a change (`--report EVIDENCE.md` to share). `gauntlet check .` re-checks the last run;
  "stale" means run again.
- Exit codes: 0 pass; 1 gate failed; 2 refused or error (read the message); 3 spec awaiting approval.
- Fix the cause: split complex functions, add missing tests, strengthen tests that let mutants survive. Never add
  ignore comments (`# pragma: no cover|no mutate`, `nolint`, `nosec`), coverage `omit`, or relax a limit.
- Agent loop: `gauntlet loop . --requirement "..."` writes a spec and stops (exit 3); show it and wait for approval.
  Then `gauntlet loop . --spec <approved.feature>` writes `.gauntlet-loop/loop.patch` and `EVIDENCE.md`. It needs
  `agent_command` in the policy and `CLAUDE_CODE_OAUTH_TOKEN` in that command's environment; never print or store it.
- Dart: `harden: SKIPPED` fails unless the policy sets `allow_skipped_gates = true`. Tell the user; never set it.
- Report gate output verbatim. The user reviews the patch (control files first) and applies it.
