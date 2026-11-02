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

## Let an agent implement an approved spec

1. Set `agent_command` and `agent_env` in your policy ([example](../examples/policy.toml)). With Docker, also build
   [`examples/agent.Dockerfile`](../examples/agent.Dockerfile) and set `docker_image_agent`.
2. Write a spec. It lands in `.gauntlet-loop/spec.feature` and the command exits `3`:

   ```sh
   gauntlet loop . --requirement "Reject uploads over 10 MB"
   ```

3. Edit the spec, then implement it:

   ```sh
   gauntlet loop . --spec .gauntlet-loop/spec.feature
   ```

4. Review `.gauntlet-loop/loop.patch` (control files first), then `git apply .gauntlet-loop/loop.patch`.

## Choose the sandbox

gauntlet prefers Workshop, else Docker. In your policy, set `sandbox = "docker"` or `"workshop"` to force one,
`container_cli = "podman"` for Podman, `docker_network = "none"` to cut off the network.

## Use your own toolchain

If the stock image can't build your project, make the artifacts yourself:

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
go = "gauntlet_go:LANGUAGE"
```

The `Language` fields say which files are source and tests, the fixed sandbox `steps`, how to read the coverage and
mutation artifacts, imports and comments for the arch and exclusion gates, and a starter `gauntlet.toml`. Core never
imports a plugin; installing it next to `gauntlet-core` is enough.
