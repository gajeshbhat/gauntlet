# Security model

## What gauntlet defends against

| Threat | Defence |
|---|---|
| An agent weakening its own rules | Limits live in your policy file outside the repo; `gauntlet.toml` may only tighten them and can be pinned by hash. `loop` reads config from your repo, never from the agent's workspace. |
| A gate passing because it checked nothing | Empty coverage, a scope matching nothing, or no layers is an error (exit 2). |
| Stale or swapped results | Artifacts are hashed and bound to the source (HEAD plus every tracked and untracked file) in a manifest; any edit to either is refused. |
| Reading outside the project | Paths from coverage data, specs and symlinks must resolve inside the project root; inputs are size-capped; hostile input exits 2, not with a stack trace. |
| Hiding code from the gates | Exclusion comments are budgeted (the patterns list every ignore hint the pinned coverage tool honours); coverage `omit`/`include`/`exclude_*` and mutmut `do_not_mutate` are refused in `pyproject.toml`, `.coveragerc`, `setup.cfg` and `tox.ini`; for other languages build settings that steer coverage (`.c8rc`, runsettings and MSBuild, pom JaCoCo settings, `.cargo/config`, ...) are reported. A source file absent from the report counts as 0%, and a function with branches but no measured lines counts as uncovered. |
| Running project code on your machine | Gates only read artifacts. Tests, mutation runs and agents execute only in a sandbox (Workshop or Docker), on a private copy of the repo. Docker containers run as your uid with no capabilities, `no-new-privileges`, a PID limit, an optional memory limit and a hard timeout. |
| Commands chosen by the repo | Commands, tool versions and output names are fixed in gauntlet. The agent command comes from your policy; secrets are passed by environment variable name, never by value. |
| Git being turned against us | Git is only asked for file names; contents are hashed in Python, so no diff, textconv or clean/smudge filter from repo config or `.gitattributes` ever runs. |
| An agent landing changes directly | `loop` returns a patch; edits to control files (`gauntlet.toml`, CI, `pyproject.toml`, `.workshop/`, ...) are flagged first. |

## What it does not defend against

- **Forged numbers.** Tests running in the sandbox can write any coverage or mutation result. The sandbox protects your
  host, not the measurements. Read the spec the tests encode.
- **A sandbox escape or a hostile payload.** Containers have network access by default (dependencies and agents need it;
  `docker_network = "none"` cuts it), and the Workshop user has sudo. On Linux, access to the Docker daemon is itself
  root-equivalent for whoever can use it. Do not run untrusted code with secrets in reach.
- **Hidden code outside the patterns.** Settings or hints gauntlet does not know about (an unusual build file, a hint inside
  a multi-line construct) still hide code; the pragma patterns match line by line. Dart `=>` functions are not scored.
- **Unpinned transitive dependencies.** Tool versions are pinned and the C++ tools are hash-locked, but the other coverage
  tools (c8, cargo-llvm-cov, Dart `coverage`, coverlet, JaCoCo) pull their own dependencies unhashed, and the project's
  dependencies resolve as the project says (npm, Cargo, Dart use lockfiles; Maven and NuGet do not).
- **Code outside functions.** CRAP scores functions. Top-level statements (scripts, module bodies) are not scored, except
  in Dart where unrun lines outside any function are flagged.
- **A narrowed mutation scope.** mutmut's `source_paths`/`paths_to_mutate` and `pytest --cov-config` live in the repo and
  are not policed. Compare the mutant count in the evidence report with the size of the code.
- **An incomplete spec.** Gates show the code meets the stated constraints, not that the constraints are enough.
- **Mutation-tool noise.** Reported kills and survivors are samples, not proofs.

Report a vulnerability by opening a private security advisory on the repository.
