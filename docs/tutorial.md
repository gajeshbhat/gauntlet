# Tutorial: your first gauntlet run

You will install gauntlet, run it on a project, read the result, fix a failure, and run it again. About 15 minutes.

## 1. Install

You need `git` and [`uv`](https://docs.astral.sh/uv/), plus a sandbox for running project code:

- Ubuntu / Linux: `sudo snap install workshop --classic` ([Canonical Workshop](https://snapcraft.io/workshop))
- Linux, macOS, Windows: [Docker](https://docs.docker.com/get-docker/) (or Podman, or Colima)

```sh
uv tool install git+https://github.com/gajeshbhat/gauntlet
gauntlet --version
```

## 2. Point it at a project

Use any Python, Go, JavaScript, C#, Java, Rust, C/C++ (CMake) or Dart project that is a git repository.

```sh
cd your-project
gauntlet init .
```

`init` detects the language and writes `gauntlet.toml`. It never overwrites one.

## 3. Run the gauntlet

```sh
gauntlet run . --report EVIDENCE.md
```

gauntlet copies your tree, runs the tests with coverage and the mutation tool inside the sandbox, copies the results
to `.gauntlet/`, stamps them, and runs every gate. The output looks like this:

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
gauntlet run .
```

The run passes with exit `0`. `EVIDENCE.md` holds a report you can attach to a pull request.

## Next

- Run it in CI, or on changed lines only: [how-to guides](how-to.md).
- Let an agent write the code against a spec you approve: [the agent loop](how-to.md#let-an-agent-implement-an-approved-spec).
