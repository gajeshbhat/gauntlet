# Tutorial: your first gauntlet run

You will install gauntlet, run it on a project, read the result, fix a failure, and run it again. About 15 minutes.

## 1. Install

You need:

- `git`.
- [`uv`](https://docs.astral.sh/uv/). gauntlet needs Python 3.12 or later; uv fetches it if you lack it.
- A sandbox, where your project's code runs:
  - Linux: [Canonical Workshop](https://snapcraft.io/workshop), `sudo snap install workshop --classic`.
  - Any OS: [Docker](https://docs.docker.com/get-docker/) (Docker Desktop or Colima) or Podman.

gauntlet uses Workshop if it is installed, else Docker. For Podman, set `container_cli = "podman"` in your policy
([choose the sandbox](how-to.md#choose-the-sandbox)).

Install gauntlet and check that it works:

```sh
uv tool install git+https://github.com/gajeshbhat/gauntlet
gauntlet --version
```

`--version` prints `gauntlet` and its version. If the repository is private to you, install from
`git+ssh://git@github.com/gajeshbhat/gauntlet` instead.

## 2. Point it at a project

Use a git repository in any [supported language](reference.md#languages).

```sh
cd your-project
gauntlet init .
```

`init` detects the language and writes `gauntlet.toml`. It never overwrites one. If it finds no language, or more
than one, it stops: write `gauntlet.toml` yourself with one line, such as `language = "go"`.

## 3. Run the gauntlet

```sh
gauntlet run . --report EVIDENCE.md
```

gauntlet copies your tree, runs the tests with coverage and the mutation tool inside the sandbox, copies the results
to `.gauntlet/`, stamps them, and runs every gate. The first run is slow: the sandbox fetches its image and tools.
The output looks like this:

```
produced coverage.json, mutmut-results.txt
arch: skipped (no layers configured)
src/app/parse.py:12: parse CRAP 17.8 > 8 (complexity 5, coverage 20%)
clean: 41 function(s) checked, 1 over CRAP 8
exclusions: 0 comment(s) (budget 10), 0 config exclude(s)
mutation score 84.0% < 90%
```

Each failure line names the file, the line and the reason. The exit code is `1`: a gate failed.

## 4. Fix the cause

- **CRAP too high**: the function is complex and poorly tested. Test its branches, or split it.
- **Mutation score too low**: the tests run code without checking its result. Strengthen the assertions the survivor
  list points at.

Do not add ignore comments or relax a limit: the `exclusions` gate counts those.

## 5. Check again

```sh
gauntlet run . --report EVIDENCE.md
```

The run passes with exit `0`. `EVIDENCE.md` holds a report you can attach to a pull request.

## Next

- Run it in CI, or on changed lines only: [how-to guides](how-to.md).
- Let an agent write the code against a spec you approve: [the agent loop](how-to.md#let-an-agent-implement-an-approved-spec).
