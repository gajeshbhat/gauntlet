# Security model

## What gauntlet defends against

| Threat | Defence |
|---|---|
| An agent weakening its own rules | Limits live in your policy file outside the repo; `gauntlet.toml` may only tighten them and can be pinned by hash. `loop` reads config from your repo, never from the agent's workspace. |
| A gate passing because it checked nothing | Empty coverage, a scope matching nothing, or no layers under `gauntlet arch` is an error (exit 2). Under `check` and `run` a missing `[layers]` is reported as skipped; set `require_arch = true` in the policy to make it fail. |
| Stale or swapped results | Artifacts are hashed and bound to the source (HEAD plus every tracked and untracked file) in a manifest; any edit to either is refused. |
| Reading outside the project | Paths from coverage data, specs and symlinks must resolve inside the project root; inputs are size-capped; hostile input exits 2, not with a stack trace. |
| Hiding code from the gates | Exclusion comments are budgeted (the patterns list every ignore hint the pinned coverage tool honours); coverage `omit`/`include`/`exclude_*` and mutmut `do_not_mutate` are refused in `pyproject.toml`, `.coveragerc`, `setup.cfg` and `tox.ini`. Source files are listed through git (tracked and untracked, not ignored), whatever their directory is called. A source file absent from the report counts as 0%, and a function with branches but no measured lines counts as uncovered. |
| Running project code on your machine | Gates only read artifacts. By default tests and mutation runs execute on your machine, in a private copy of the repo (0700 temp dir), with a minimal environment and a hard timeout: they are not isolated, and `run` says so. Set `sandbox = "openshell"` (or `--sandbox openshell`) to run them in an OpenShell sandbox instead: no host mount, no network except the package index. `loop` runs an agent that executes arbitrary commands, so it refuses to start unless the sandbox is OpenShell or the policy sets `allow_unsandboxed_agent = true`. |
| Commands chosen by the repo | Commands, tool versions and output names are fixed in gauntlet. The agent command comes from your policy; secrets are passed by environment variable name, never by value. |
| Git being turned against us | Git is only asked for file names; contents are hashed in Python, so no diff, textconv or clean/smudge filter from repo config or `.gitattributes` ever runs. In `loop` the workspace's git dir lives beside it, outside what the agent can write, so a filter planted in the workspace's `.git/config` never runs on the host. |
| An agent landing changes directly | `loop` returns a patch; edits to control files (`gauntlet.toml`, CI, `pyproject.toml`, ...) are flagged first. |

## What it does not defend against

- **Forged numbers.** Tests can write any coverage or mutation result, sandboxed or not. A sandbox protects your host,
  not the measurements. Read the spec the tests encode.
- **Hostile code on the default setting.** With `sandbox = "local"`, project code runs as you: it can read your files
  and use your network, and its environment is only scrubbed, not sealed. An agent run locally can also edit the git
  directory beside its workspace. Do not run untrusted code locally, and do not run it with secrets in reach. A sandbox
  escape from OpenShell is that project's to defend.
- **Hidden code outside the patterns.** Settings or hints gauntlet does not know about (an unusual build file, a hint inside
  a multi-line construct) still hide code; the pragma patterns match line by line.
- **Unpinned transitive dependencies.** Tool versions are pinned, but the tools pull their own dependencies unhashed,
  and the project's dependencies resolve as the project says.
- **Code outside functions.** CRAP scores functions. Top-level statements (scripts, module bodies) are not scored.
- **A planted or narrowed mutation report.** The mutation report is removed just before the mutation run, but repo code
  runs in the same place as the tools and can still forge it (see "Forged numbers").
- **A narrowed mutation scope.** mutmut's `source_paths`/`paths_to_mutate` and `pytest --cov-config` live in the repo and
  are not policed. Compare the mutant count in the evidence report with the size of the code.
- **An incomplete spec.** Gates show the code meets the stated constraints, not that the constraints are enough.
- **Mutation-tool noise.** Reported kills and survivors are samples, not proofs.

Report a vulnerability by opening a private security advisory on the repository.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting (Security tab, "Report a vulnerability") and do not open a public issue.
Include the gauntlet version and a minimal reproduction. Expect an acknowledgement within a week.
