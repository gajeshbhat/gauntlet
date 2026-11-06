# How-to guides

## Check only changed code

```sh
gauntlet run . --only src/app/parse.py:10-40 --only src/app/new/
```

## Re-check without re-running tests

```sh
gauntlet check .
```

Reads the last run in `.gauntlet/`. "stale" means the source changed: run again.

## Set your own limits

Copy [`examples/policy.toml`](../examples/policy.toml) to `~/.config/gauntlet/policy.toml` and edit it. To refuse
edits to a repo's `gauntlet.toml`, run `gauntlet pin .`, then set `require_pin = true`.

## Use gauntlet in CI

Keep the policy outside the repo:

```sh
gauntlet run . --policy /etc/gauntlet/policy.toml --json results.json --report EVIDENCE.md
```

Non-zero exit fails the job ([exit codes](reference.md#exit-codes)).

## Run in an OpenShell sandbox

By default tests and mutation runs execute on this machine, in a throwaway copy of the repo with a minimal
environment. To isolate them, start an [OpenShell](https://github.com/NVIDIA/OpenShell) gateway and install gauntlet with the
`openshell` extra next to `python` (`gauntlet-core[openshell,python]`, otherwise as in the README), then:

```sh
gauntlet run . --sandbox openshell   # or: sandbox = "openshell" in your policy
```

The sandbox starts from the language's image, has no network except the package index, and is deleted afterwards.
Dependencies your project needs from elsewhere will not install.

## Choose the mutation tool

`mutmut` is the default. For projects mutmut cannot handle, set `tool = "cosmic-ray"` under `[mutation]` in
`gauntlet.toml`. Cosmic Ray runs one mutant at a time per worker, with one worker per CPU, each in its own copy of the
snapshot, on this machine or in the OpenShell sandbox. Both tools feed the same gate and the same floor.

## Use your own toolchain

If the stock setup can't build your project, make the artifacts yourself:

```sh
pytest --cov=src --cov-branch --cov-report=json:coverage.json
mutmut run && mutmut results --all true > mutmut-results.txt
gauntlet stamp .
gauntlet check . --artifacts .
```

`--artifacts .` stops `check` reading `.gauntlet/`. File names: [languages](reference.md#languages).

## Write a language plugin

A plugin is a package that exposes one `gauntlet.plugin.Language` value as a `gauntlet.languages` entry point (see
`packages/gauntlet-python` for a full example):

```toml
[project]
dependencies = ["gauntlet-core"]

[project.entry-points."gauntlet.languages"]
mylang = "gauntlet_mylang:LANGUAGE"
```

The `Language` fields say which files are source and tests, the fixed `steps` (given the project and output directories), how to read the coverage and
mutation artifacts, imports and comments for the arch and exclusion gates, and a starter `gauntlet.toml`. Core never
imports a plugin; installing it next to `gauntlet-core` is enough.
