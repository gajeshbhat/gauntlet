# Reference

## Commands

`gauntlet COMMAND [ROOT] [options]`. `ROOT` defaults to `.`.

- `init`: write a starter `gauntlet.toml` (never overwrites).
- `run`: sandboxed tests, coverage and mutation, then all gates. Results go to `.gauntlet/`.
- `check`: `arch` (if layers are set), `clean`, `exclusions` on existing results.
- `arch`, `clean`, `harden`, `exclusions`, `spec`: one gate.
- `stamp`: bind artifacts to the current source.
- `pin`: record `gauntlet.toml`'s hash in your policy.
- `diagram`: print a Mermaid graph of the layers.
- `loop --requirement TEXT`: write a spec, then stop (exit 3).
- `loop --spec FILE`: implement an approved spec; writes `loop.patch` and `EVIDENCE.md`.

## Options

- `--only PATH[:LO-HI]`: limit to a file, `DIR/` or line range; repeatable.
- `--artifacts DIR`: read artifacts here (default: `.gauntlet/` after a run, else `ROOT`).
- `--source DIR`: git checkout the artifacts came from (default: `ROOT`).
- `--policy FILE`: policy file (default: `~/.config/gauntlet/policy.toml`).
- `--json FILE`: also write results as JSON.
- `--report FILE`: also write an `EVIDENCE.md` report.
- `--feature FILE`: `spec` only; the Gherkin file (default: `ROOT/spec.feature`).
- `--out DIR`: output directory (`run`: `ROOT/.gauntlet`; `loop`: `ROOT/.gauntlet-loop`).

## Exit codes

- `0`: every gate passed.
- `1`: a gate failed.
- `2`: refused or error (bad config, missing or stale artifacts, empty gate).
- `3`: `loop` wrote a spec and awaits approval.

## Gates

- `clean`: fails when a function's CRAP score exceeds 8 (default).
- `harden`: fails when the mutation score is under 90% (default).
- `arch`: fails when an import points outward through the layers.
- `exclusions`: fails when ignore comments exceed 10 (default), or build settings hide code from the checks.
- `spec`: fails when the Gherkin spec is malformed, or a scenario lacks an existing `@test(path::name)`.

## Languages

Python only: coverage.py and mutmut; artifacts `coverage.json`, `mutmut-results.txt`. Other languages (Go, JavaScript/TypeScript, C#, Java, Rust, C/C++, Dart) are archived at tag `v0.1-multilang` and branch `archive/multilang`. Complexity comes from [lizard](https://github.com/terryyin/lizard).

## `gauntlet.toml`

In the project root. Unknown keys are errors.

```toml
language = "python"            # required
src = "src"                    # where module names are rooted (default ".")

[crap]
max = 8                        # may only tighten the policy's crap_ceiling

[mutation]
min_score = 90                 # may only tighten the policy's mutation_floor

[layers]                       # optional: imports may only point down this list
order = ["app.web", "app.service", "app.domain"]
roots = ["pkg_a/src", "pkg_b/src"]   # optional: several source roots instead of `src`; each must hold a layered module
forbid = ["app.domain -> requests", "app.web -> app except app.web, app.service"]   # optional: banned imports
```

## `policy.toml`

Your rules, in `~/.config/gauntlet/policy.toml`, outside any repository. Every key and default is in
[`examples/policy.toml`](../examples/policy.toml).
