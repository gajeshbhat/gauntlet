---
name: gauntlet
description: Prove that code written by an AI agent works, instead of reading it. Runs CRAP (complexity x coverage), mutation, architecture, exclusion-budget and spec gates on a Python, Go, JavaScript/TypeScript, C#, Java, Rust, C/C++ or Dart project in a sandbox (Workshop or Docker), and can run a Specifier/Coder/Fixer agent loop that ends in a patch for the user to review. Use when the user says "gauntlet", "prove this works", "run the quality gates", or wants a spec-first agent workflow.
argument-hint: [init|run|check|loop] [path]
---
Work from the project root. The rules the user set live in `~/.config/gauntlet/policy.toml`: never edit it, never copy it
into a repository, and never edit a repo's `gauntlet.toml` to make a gate pass.

## Before the first use
1. `command -v gauntlet || uv tool install git+https://github.com/gajeshbhat/gauntlet` (private repo: use `git+ssh://git@github.com/gajeshbhat/gauntlet`).
2. `run` and `loop` execute project code, so they need a sandbox: Canonical Workshop on Linux
   (`sudo snap install workshop --classic`) or Docker/Podman on Linux, macOS and Windows. Check `command -v workshop docker`;
   tell the user what to install (never run `sudo` yourself). With Docker, `loop` also needs `docker_image_agent` in the policy.
3. No `gauntlet.toml` yet: `gauntlet init .` writes a starter one (the language is detected).

## Use
- Prove a change: `gauntlet run .` (tests, coverage and mutation in a sandbox, then every gate; results in `.gauntlet/`).
  Add `--report EVIDENCE.md` for a shareable report.
- Re-check existing results: `gauntlet check .`. "stale" means the source changed: run `gauntlet run .` again.
- Exit codes: 0 pass; 1 a gate failed (fix the code or tests); 2 refused or error (read the message); 3 spec awaiting approval.
- Fix failures at the cause: split complex functions, write the missing test, strengthen a test that lets a mutant survive.
  Never add `# pragma: no cover|no mutate`, `nolint`, `nosec`, coverage `omit`, or relax a limit: the exclusion gate fails it.
- Spec-first agent loop (the agent runs in the sandbox, your tree is untouched):
  1. `gauntlet loop . --requirement "..."` writes a Gherkin spec and stops (exit 3). Show it to the user and wait for approval.
  2. `gauntlet loop . --spec <approved.feature>` implements it and writes `.gauntlet-loop/loop.patch` and `EVIDENCE.md`.
  The agent needs the user's `agent_command` in the policy and `CLAUDE_CODE_OAUTH_TOKEN` in the environment of that one
  command (from `claude setup-token`); never print or store the token.
- Languages without a mutation tool (everything but Python and Go) show `harden: SKIPPED` and fail unless the user's
  policy sets `allow_skipped_gates = true`; tell the user, never set it yourself. Build settings that hide code from coverage
  (`.c8rc`, runsettings, pom/JaCoCo, cargo config, ...) are reported by the exclusions gate; never add them to pass.
- Report gate output verbatim. Do not describe a failure as a pass.

The user reviews the patch (control files such as CI and `gauntlet.toml` first) and applies it.
