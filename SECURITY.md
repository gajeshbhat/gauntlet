# Security model

What gauntlet defends against, and what it does not.

## Defended
- **An agent weakening its own rules.** Limits live in your policy file outside the repo; `gauntlet.toml` can only tighten
  them, and can be pinned by hash. The loop reads the config from the source repo, never from the agent's workspace.
- **Silent passes.** A gate that evaluated nothing (empty coverage, scope matching nothing, no layers) is an error.
- **Stale or swapped results.** Artifacts are hashed and bound to the source (HEAD + diff + untracked files) in a
  manifest; edits to either are refused.
- **Escaping the project.** Paths named by coverage data, specs or symlinks must resolve inside the project root.
  Hostile or oversized inputs are size-capped and fail with exit 2, not a stack trace.
- **Hiding code from the gates.** Exclusion comments are budgeted; coverage `omit`/`exclude_*` and mutmut `do_not_mutate` are
  refused in pyproject.toml, .coveragerc, setup.cfg and tox.ini.
- **Running target code on the host.** Gates only read artifacts. Tests, mutation runs and agents execute only in a
  Workshop sandbox, on a private copy of the repo. The agent cannot edit the sandbox definition or the source mid-run.
- **Commands chosen by the repo.** Commands, tool versions and output names are fixed in gauntlet; the agent command
  comes from your policy; env vars are passed by name, never by value.
- **Our own git calls being hijacked** by repository config, `.gitattributes` filters or environment: git is only asked
  for names; file contents are hashed in Python, so no diff, textconv or clean/smudge filter runs.
- **Agents landing changes directly.** The loop returns a patch; control files it touches (gauntlet.toml, CI,
  pyproject, .workshop/...) are flagged for review first.

## Not defended
- **Narrowed mutation scope.** mutmut's `source_paths`/`paths_to_mutate` live in the repo and are not policed; compare the
  mutant total in the evidence report with the size of the code. `pytest --cov-config` files are not parsed either.
- **Forged numbers.** Tests that run in the sandbox can write any coverage or mutation result. The sandbox protects the
  host, not the measurements. Read the spec the tests encode.
- **A hostile sandbox escape.** The Workshop user has sudo and network access inside the container; do not run
  untrusted code with secrets in reach.
- **Spec completeness.** Gates prove the code meets the stated constraints, not that the constraints are enough.
- **Mutation noise.** Tool-reported survivors and kills are samples, not proofs (we saw one false LIVED in gremlins).
