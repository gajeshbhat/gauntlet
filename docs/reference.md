# Reference

## Commands

`gauntlet COMMAND [ROOT] [options]`. `ROOT` defaults to `.`.

- `init`: write a starter `gauntlet.toml` (never overwrites).
- `run`: tests, coverage and mutation on a private copy, then all gates. Results go to `.gauntlet/`.
- `check`: `arch` (if layers are set), `clean`, `exclusions` on existing results.
- `arch`, `clean`, `harden`, `exclusions`, `spec`: one gate.
- `stamp`: bind artifacts to the current source.
- `pin`: record `gauntlet.toml`'s hash in your policy.
- `diagram`: print a Mermaid graph of the layers.

## Options

- `--only PATH[:LO-HI]`: limit to a file, `DIR/` or line range; repeatable. A function with any line in range is checked.
- `--changed [REF]`: limit to the lines that differ from commit `REF` (default `HEAD`), untracked files included. Adds to `--only`.
- `--artifacts DIR`: read artifacts here (default: `.gauntlet/` after a run, else `ROOT`).
- `--source DIR`: git checkout the artifacts came from (default: `ROOT`).
- `--policy FILE`: policy file (default: `~/.config/gauntlet/policy.toml`).
- `--json FILE`: also write results as JSON.
- `--report FILE`: also write an `EVIDENCE.md` report.
- `--feature FILE`: `spec` only; the Gherkin file (default: `ROOT/spec.feature`).
- `--sandbox local|openshell`: where project code runs for `run` (default: the policy's, else `local`).
- `--out DIR`: output directory (`run`: `ROOT/.gauntlet`).

## Exit codes

- `0`: every gate passed.
- `1`: a gate failed.
- `2`: refused or error (bad config, missing or stale artifacts, empty gate).

## Gates

- `clean`: fails when a function's CRAP score exceeds 8 (default).
- `harden`: fails when the mutation score is under 90% (default). Each survivor is printed as
  `file:line: mutant: status [old line -> new line]`; `file:line` is the function it is in.
- `arch`: fails when an import points outward through the layers.
- `exclusions`: fails when ignore comments exceed 10 (default), or build settings hide code from the checks.
- `spec`: fails when the Gherkin spec is malformed, or a scenario lacks an existing `@test(path::name)`.

## Languages

Python only: coverage.py and mutmut (or Cosmic Ray, see `[mutation] tool`); artifacts `coverage.json`, `mutmut-results.txt`. Complexity comes from [lizard](https://github.com/terryyin/lizard).

## `gauntlet.toml`

In the project root. Unknown keys are errors.

```toml
language = "python"            # required
src = "src"                    # where module names are rooted (default ".")

[crap]
max = 8                        # may only tighten the policy's crap_ceiling

[mutation]
min_score = 90                 # may only tighten the policy's mutation_floor
tool = "mutmut"                # or "cosmic-ray": one mutant per CPU, in worker copies of the project

[layers]                       # optional: imports may only point down this list
order = ["app.web", "app.service", "app.domain"]
roots = ["pkg_a/src", "pkg_b/src"]   # optional: several source roots instead of `src`; each must hold a layered module
forbid = ["app.domain -> requests", "app.web -> app except app.web, app.service"]   # optional: banned imports
```

## `policy.toml`

Your rules, in `~/.config/gauntlet/policy.toml`, outside any repository. Every key and default is in
[`examples/policy.toml`](../examples/policy.toml).
