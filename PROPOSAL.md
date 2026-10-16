# Gauntlet: agent-agnostic quality pipeline (proposal)

Status: draft for discussion. Nothing is built.

## Problem
Long steering prompts get lost in context. Quality should come from deterministic tools that fail loudly,
not from instructions an agent may forget. Inspired by Robert C. Martin's "Gauntlet": ephemeral agents,
each born for one task with a clean context, separated by hard gates.

## Goals
- Works with any coding agent (Claude Code, Codex, Cursor, Gemini CLI...): core is plain CLI + config; agents are thin adapters.
- Offline, no hosted services or API keys beyond the agent's own login.
- Minimal prompts (under 15 lines each); rules live in tools and config.
- Reuse what exists: the Workshop (LXD) sandbox from `workshop-agent`, `vm-test` for LXD builds.

## Non-goals
- Not a new agent or an IDE plugin. Not a replacement for Spec Kit (`specify`) when a full written spec is wanted.
- No GUI. No cloud runner.

## Pieces
1. **`gauntlet.toml`** (per repo): language, commands, thresholds, architecture layers.
   ```toml
   language = "python"
   [crap]    max = 8            # raised from 4-5 for AI authors
   [mutation] min_score = 90
   [layers]  order = ["web", "service", "domain"]   # deps flow one way
   ```
2. **Gates** (deterministic, exit non-zero, JSON on stdout), one adapter per language:
   - `clean`: CRAP = CC^2 * (1-cov)^3 + CC; fails above threshold. Python: radon + coverage. Go: gocyclo/gocognit + cover.
   - `harden`: mutation testing. Python: mutmut. Go: gremlins.
   - `arch`: boundaries. Python: import-linter. Go: depguard (already in golangci-lint).
   - `qa`: run Gherkin features (pytest-bdd/behave; godog).
3. **Agents** (3 LLM roles, ephemeral): `specifier` (requirements -> Gherkin + QA procedure), `coder` (function, then test),
   `fixer` (gets only a failing gate's output). Prompts in `agents/*.md`.
4. **Loop**: `gauntlet loop "<requirement>"`: specifier -> coder -> gates -> on failure spawn fixer with the gate output only -> repeat max N.
   Every agent runs as a fresh process (`workshop exec agent -- <agent cmd>`), so context is clean and the host is untouched.
5. **Adapters** (`gauntlet install --agent X`): render the same role prompts into each agent's native form
   (Claude: `.claude/agents/` + Stop hook running `gauntlet check`; others: AGENTS.md snippet + git pre-commit).
   The agent CLI is a config template (`claude -p`, `codex exec`...), so swapping agents is one line.
6. **Diagrams**: `gauntlet diagram` emits Mermaid (layer graph, violations highlighted) into `docs/`. Text, offline, renders on GitHub.

## Proposed implementation
One Python file using stdlib (`tomllib`, `subprocess`), run with `uv run`. Gate tools are pinned dev dependencies of the target repo.
Reason: tiny, readable, no build step. Upgrade path: split per-language adapters once a third language appears.

## Milestones
- M0: `clean` + `arch` gates for Python, proven on `snapcraft.io` (CRAP script + import-linter).
- M1: `harden` + `loop` with Claude Code in a Workshop sandbox.
- M2: Go adapters (pilot on a small Go repo, not lxd); Codex adapter.
- M3: `qa` gate, `specifier` with human-approved SPEC, `gauntlet report` (EVIDENCE), `diagram`.
- M4: optional layers (property-based, supply-chain, secrets) and the fresh-context verifier.

## Verification
Each gate has a self-test against a fixture repo (a deliberately complex function must fail `clean`; an import in the wrong direction must fail `arch`).

## Credits and what we borrow
Gauntlet builds on two sources; credit where it is due.
- **Robert C. Martin ("Uncle Bob")**: the approach itself. Do not read the agents' code; surround them with extreme
  constraints (unit and Gherkin tests, QA procedures, quality metrics, mutation testing, coverage) and make the code run the gauntlet.
  Source for our design: his interview with Matt Pocock, https://youtu.be/zcLPGC-tvgk
  (CRAP thresholds raised for agents, ephemeral agents, deep modules), and his post
  https://x.com/unclebobmartin/status/2080257779395154409
- **AmazingAng, `old-coder`** (MIT): https://github.com/amazingang/old-coder. A markdown skill that applies the same idea to
  coding agents. We borrow ideas only, no text or code copied, and adapt them to a deterministic CLI:
  - A human-approved SPEC (examples of must / must-not behavior) before any code is written; the Specifier output needs approval.
  - Fail closed: a gate that did not run, or found nothing to check (no coverage file, no mutants), is a failure, never a pass.
  - Negative controls: every gate ships with a known-bad fixture proving it can fail ("the gauntlet needs its own gauntlet").
  - An EVIDENCE report (`gauntlet report`) rebuilt from gate output, rerunnable with one command.
  - Candidate extra layers: property-based tests, supply-chain audit, secret scan.
  - A fresh-context verifier agent that sees only the SPEC and the evidence.

Where we differ: old-coder is instructions the agent may follow; Gauntlet is a runner with exit codes, plus CRAP and architecture
gates and Workshop-sandboxed ephemeral agents.

## Decisions (agreed)
- Name `gauntlet`; repo at `~/git/gauntlet`.
- Python 3.12 project managed by `uv`; ruff, pyright (strict), pytest with 100% branch coverage enforced by `./check.sh`.
- Workshop is **required**: every agent runs via `workshop exec`.
- Pilot (validates gates on real code, which fixtures cannot): upstream `canonical/lxd`.
  Pilot issue: canonical/lxd#15874 "disk propagation not working" (chosen by user; supersedes #19162).
  LXD builds/tests run in the `lxd-test-vm` VM, so the Go adapter runs gates there while agents stay in Workshop.
