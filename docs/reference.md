# Reference

## Commands

`gauntlet COMMAND [ROOT] [options]`. `ROOT` defaults to `.`.

| Command | What it does |
|---|---|
| `init` | write a starter `gauntlet.toml` (the language is detected; never overwrites) |
| `run` | sandboxed tests, coverage and mutation, then `check` and `harden`; results in `.gauntlet/` |
| `check` | `arch` (if layers are set), `clean` and `exclusions` on existing results |
| `arch`, `clean`, `harden`, `exclusions`, `spec` | one gate on existing results |
| `stamp` | bind artifacts to the current source |
| `pin` | record `gauntlet.toml`'s hash in your policy |
| `diagram` | print a Mermaid graph of the layers, violations marked |
| `loop --requirement TEXT` | a Specifier agent writes a spec, then stops (exit 3) |
| `loop --spec FILE` | Coder and Fixer agents implement an approved spec; writes `loop.patch` and `EVIDENCE.md` |

| Option | Meaning |
|---|---|
| `--only PATH[:LO-HI]` | limit `clean`, `harden` and `exclusions` to a file, a `DIR/` or a line range; repeatable |
| `--artifacts DIR` | where artifacts are read from (default: `.gauntlet/` after a run, else `ROOT`) |
| `--source DIR` | the git checkout the artifacts were produced from (default: `ROOT`) |
| `--policy FILE` | policy file (default: `~/.config/gauntlet/policy.toml`) |
| `--json FILE` | also write the gate results as JSON |
| `--report FILE` | also write an evidence report (Markdown) |
| `--feature FILE` | `spec`: the Gherkin file (default: `ROOT/spec.feature`) |
| `--out DIR` | `run`: where artifacts go (default: `ROOT/.gauntlet`); `loop`: its output (default: `ROOT/.gauntlet-loop`) |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every gate passed |
| `1` | a gate failed |
| `2` | refused or error: bad config, missing or stale artifacts, a gate that checked nothing, malformed input |
| `3` | `loop` wrote a spec and waits for your approval |

## Gates

| Gate | It fails when |
|---|---|
| `clean` | a function's CRAP score, complexity² × (1 − coverage)³ + complexity, is over the limit (default 8). A source file missing from the coverage report counts as 0%. |
| `harden` | the mutation score is under the floor (default 90%) |
| `arch` | an import points outward through the declared layers (Python and Go only) |
| `exclusions` | ignore comments exceed the budget (default 10), or build settings hide code from coverage or mutation |
| `spec` | the Gherkin spec is malformed, or a scenario has no `@test(path::name)` that exists |

## Languages

| Language | `language =` | Tests and coverage | Mutation (`harden`) | Artifacts | Proven end to end |
|---|---|---|---|---|---|
| Python | `python` | pytest + coverage.py | mutmut | `coverage.json`, `mutmut-results.txt` | yes (gauntlet runs itself) |
| Go | `go` | `go test -coverprofile` | gremlins | `cover.out`, `imports.txt`, `mutation.json` | yes |
| JavaScript, TypeScript | `javascript` | `npm ci --ignore-scripts`, `npm test` under c8 | Stryker | `lcov.info`, `stryker.json` | JavaScript only (1) |
| C# | `csharp` | `dotnet test` + coverlet (2) | Stryker.NET | `coverage.cobertura.xml`, `stryker-report.json` | yes |
| Java | `java` | Maven + JaCoCo, no pom edits | PIT | `jacoco.xml`, `mutations.xml` | yes |
| Rust | `rust` | cargo-llvm-cov | cargo-mutants | `lcov.info`, `mutants-outcomes.json` | yes |
| C, C++ (GCC) | `cpp` | CMake + gcov + gcovr (3) | universalmutator, built-in rules | `lcov.info`, `cpp-mutants.json` | C only (5) |
| C, C++ (Clang) | `cpp-clang` (4) | CMake + Clang source-based coverage | Mull | `lcov.info`, `mull-report.json` | C only (5) |
| Dart | `dart` | `dart test` + `coverage`, no Flutter | none (6) | `lcov.info` | yes |

1. TypeScript projects are accepted but not yet proven in a real container.
2. The test project must reference the `coverlet.collector` package.
3. `init` detects `cpp` from `CMakeLists.txt`, `Makefile` or `meson.build`, but `run` builds with CMake only.
4. `cpp-clang` is never detected: set it in `gauntlet.toml`. It runs in `silkeh/clang:21-trixie` with a pinned Mull
   `.deb`, unpacked without root.
5. Proven on C projects, not yet on C++.
6. Dart has no mutation tool: `run` reports `harden` as skipped and fails, unless the policy sets
   `allow_skipped_gates = true`. lizard reads Dart through its Java reader, so `=>` functions are not scored.

Complexity comes from [lizard](https://github.com/terryyin/lizard) for every language.

## `gauntlet.toml`

In the project root. Unknown keys and wrong types are errors.

```toml
language = "python"            # required: one of the languages above
src = "src"                    # Python: where module names are rooted (default ".")

[crap]
max = 8                        # tighten only: above the policy's crap_ceiling is refused (exit 2)

[mutation]
min_score = 90                 # tighten only: below the policy's mutation_floor is refused (exit 2)

[layers]                       # optional: imports may only point down this list, outermost first
order = ["app.web", "app.service", "app.domain"]

[go]                           # Go only, all optional
packages = ["./..."]           # what the sandbox tests
mutation_dir = "internal/pkg"  # where gremlins runs
mutate_only = ["handler.go"]   # mutate just these files (relative to mutation_dir)
```

## `policy.toml`

Your rules, in `~/.config/gauntlet/policy.toml`, outside any repository. Every key, with its default:
[`examples/policy.toml`](../examples/policy.toml).

| Key | Default | Meaning |
|---|---|---|
| `crap_ceiling` | `8` | highest CRAP score allowed |
| `mutation_floor` | `90` | lowest mutation score allowed, percent |
| `max_exclusions` | `10` | budget of ignore comments |
| `allow_config_excludes` | `false` | accept coverage or mutation excludes in the repo's config |
| `allow_skipped_gates` | `false` | accept a skipped `harden` (languages with no mutation tool) |
| `allow_unstamped` | `false` | accept artifacts not bound to the current source |
| `require_pin` | `false` | refuse a `gauntlet.toml` you have not pinned |
| `agent_command`, `agent_env`, `agent_timeout`, `max_rounds` | | the agent for `loop`; secrets are passed by variable name |
| `sandbox` | `"auto"` | `"auto"`, `"workshop"` or `"docker"` |
| `container_cli`, `docker_network`, `docker_memory`, `docker_image_agent`, `[docker_images]` | | Docker backend settings |

## Files gauntlet writes

| Path | What |
|---|---|
| `.gauntlet/` | the last run's artifacts and `gauntlet-manifest.json` |
| `gauntlet-manifest.json` | hashes binding artifacts to the source (written by `stamp`) |
| `.gauntlet-loop/` | `spec.feature`, `loop.patch`, `EVIDENCE.md` and `artifacts/` from `loop` |
