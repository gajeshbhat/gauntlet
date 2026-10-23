# How-to guides

## Check only the code that changed

```sh
gauntlet run . --only src/app/parse.py:10-40 --only src/app/new/
```

`--only` limits `clean`, `harden` and `exclusions` to a file, a directory (`DIR/`) or a line range.

## Re-check results without running the tests

```sh
gauntlet check .
```

`check` reads the last run's results in `.gauntlet/`. "stale" means the source changed since that run: run again.

## Set your own limits

Copy [`examples/policy.toml`](../examples/policy.toml) to `~/.config/gauntlet/policy.toml` and edit it. A repository's
`gauntlet.toml` can tighten these limits, never weaken them. To refuse any edit to a repo's `gauntlet.toml`:

```sh
gauntlet pin .         # records the file's hash in your policy
```

Then set `require_pin = true` in the policy.

## Use gauntlet in CI

Keep the policy outside the repository the agent edits, and pass it explicitly:

```sh
gauntlet run . --policy /etc/gauntlet/policy.toml --json results.json --report EVIDENCE.md
```

Exit `0` passes the job; any other code fails it. See [exit codes](reference.md#exit-codes).

## Let an agent implement an approved spec

1. Set the agent in your policy (see `agent_command` and `agent_env` in
   [`examples/policy.toml`](../examples/policy.toml)).
2. Ask for a spec:

   ```sh
   gauntlet loop . --requirement "Reject uploads over 10 MB"
   ```

   A Specifier agent writes `.gauntlet-loop/spec.feature` and gauntlet stops with exit `3`.
3. Read and edit the spec until you approve it. Then:

   ```sh
   gauntlet loop . --spec .gauntlet-loop/spec.feature
   ```

   A Coder agent implements it in a copy of your repo. Fixer rounds run until every gate passes or `max_rounds` is used.
4. Review `.gauntlet-loop/loop.patch`. Start with the control files it flags (CI, `gauntlet.toml`, ...). Then apply it:
   `git apply .gauntlet-loop/loop.patch`.

With the Docker backend, the agent needs an image that contains it: build one from
[`examples/agent.Dockerfile`](../examples/agent.Dockerfile) and set `docker_image_agent`.

## Choose the sandbox

gauntlet uses Workshop if it is installed, else Docker. To force one, set `sandbox = "docker"` or
`sandbox = "workshop"` in your policy. For Podman, also set `container_cli = "podman"`. To cut the container off the
network, set `docker_network = "none"` (dependency downloads then fail).

On macOS and Windows, Docker Desktop and Colima run containers in a VM, and that VM is the isolation boundary. On Linux,
for more isolation, run Docker inside a Multipass or Lima VM.

## Use your own toolchain

When the stock image cannot build your project, produce the artifacts yourself, then stamp and check them:

```sh
# Go, for example:
go test -coverprofile=cover.out ./...
go list -e -f '{{.ImportPath}} {{join .Imports " "}}' ./... > imports.txt
gremlins unleash -o mutation.json .
gauntlet stamp .
gauntlet check . --artifacts .
```

Pass `--artifacts .`: after an earlier `gauntlet run`, `check` would otherwise read `.gauntlet/`.

The [artifacts table](reference.md#languages) lists each language's files. When one is missing, the error message shows
the command that makes it. `stamp` binds the artifacts to the current source, so the project must be a git repository.

## Draw the layers

```sh
gauntlet diagram . > layers.mmd
```

This prints a Mermaid graph of the `[layers]` in `gauntlet.toml`, with violations marked.
