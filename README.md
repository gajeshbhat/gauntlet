# gauntlet

**Don't read the code an AI agent wrote. Make it run a gauntlet, and read the evidence.**

gauntlet checks Python and Go projects with deterministic gates that fail loudly, and can run a Specifier → Coder → Fixer
agent loop in a sandbox that ends in a patch you review. It works on any project; no code changes needed.

| Gate | It fails when |
|---|---|
| `clean` | a function's CRAP score (complexity² × (1 − coverage)³ + complexity) is over the limit (default 8) |
| `harden` | the mutation score is under the floor (default 90%): tests let planted bugs survive |
| `arch` | an import points outward through the layers you declare |
| `exclusions` | code is hidden with `pragma: no cover`, `nolint`, `nosec` or coverage/mutmut excludes beyond a budget |
| `spec` | a Gherkin spec is malformed, or a scenario has no real test behind it |

Every gate fails closed: checking nothing is an error, never a pass. Results are bound to the exact source they came from.

## Install

You need `git` and [`uv`](https://docs.astral.sh/uv/). `run` and `loop` execute project code, so they also need a sandbox:

| Platform | Sandbox | Install |
|---|---|---|
| Ubuntu / Linux | [Canonical Workshop](https://snapcraft.io/workshop) (LXD) | `sudo snap install workshop --classic` |
| Linux, macOS, Windows | Docker (or Podman) | [Docker Desktop](https://docs.docker.com/get-docker/), Colima, or Docker Engine |

gauntlet picks Workshop if it is installed, else Docker; set `sandbox = "docker"` in your policy to force one.
On macOS and Windows, Docker Desktop and Colima run containers inside a VM, which is your isolation boundary; for more
isolation on Linux, run Docker inside a Multipass or Lima VM. Reading results with `check`, `clean`, `arch` and the
other gates needs no sandbox at all.

```sh
uv tool install git+https://github.com/gajeshbhat/gauntlet    # the CLI (private repo: git+ssh://git@github.com/gajeshbhat/gauntlet)
gauntlet --version
```

### In Claude Code

```
/plugin install gauntlet --marketplace gajeshbhat/gauntlet
```

Then ask Claude to "run the gauntlet on this project" or use `/gauntlet`. The skill checks the prerequisites above and
tells you what is missing. Needs Claude Code 2.1.275 or later.

## Use it on an existing project

```sh
cd your-project
gauntlet init .            # writes gauntlet.toml (Python or Go is detected; never overwrites)
gauntlet run . --report EVIDENCE.md
```

`run` snapshots your tree, runs tests with coverage and mutation testing **inside a sandbox**, copies the
results out, stamps them, and evaluates every gate. Exit codes: `0` pass, `1` a gate failed, `2` refused or error,
`3` spec awaiting your approval.

| Command | What it does |
|---|---|
| `gauntlet run .` | sandboxed tests + mutation, then all gates (results in `.gauntlet/`) |
| `gauntlet check .` | re-evaluate the last run's results; "stale" means the source changed |
| `gauntlet arch\|clean\|harden\|exclusions\|spec .` | one gate on existing results |
| `gauntlet loop . --requirement "..."` | a Specifier writes a Gherkin spec and **stops for your approval** (exit 3) |
| `gauntlet loop . --spec spec.feature` | Coder + Fixer rounds in a copy of your repo → `.gauntlet-loop/loop.patch` + evidence |
| `gauntlet diagram .` | Mermaid graph of your layers, violations in red |
| `gauntlet stamp .` / `pin .` | bind artifacts to the source / record `gauntlet.toml`'s hash in your policy |

Options: `--only PATH[:LO-HI]` or `DIR/` limits `clean`, `harden` and `exclusions` to part of the code (for example
changed lines); `--report FILE`, `--json FILE`, `--artifacts DIR`, `--source DIR`, `--policy FILE`.

The agent loop never touches your tree. The agent command comes from your policy, its token is passed by variable name,
and the patch flags edits to control files (CI, `gauntlet.toml`, ...) for you to review first. With the Docker backend the
agent needs an image that contains it; build one from [`examples/agent.Dockerfile`](examples/agent.Dockerfile).

## Configuration

`gauntlet.toml` in the project (strict: unknown keys are errors):

```toml
language = "python"            # or "go"
src = "src"                    # Python: where module names are rooted

[layers]                       # optional: imports may only point down this list, outermost first
order = ["app.web", "app.service", "app.domain"]

[go]                           # Go only, all optional
packages = ["./..."]           # what the sandbox tests
mutation_dir = "internal/pkg"  # where gremlins runs
mutate_only = ["handler.go"]   # mutate just these files
```

Your rules live **outside the repo**, in `~/.config/gauntlet/policy.toml` (start from
[`examples/policy.toml`](examples/policy.toml)): limits the project can tighten but never weaken, an exclusion budget,
and the agent for `loop`. This is what stops an agent from editing its own thresholds. What gauntlet does and does
**not** protect against: [SECURITY.md](SECURITY.md).

Go projects: `run` works when a stock Go image (or Workshop's Go SDK) can build the project. Otherwise produce `gocyclo.txt`,
`cover-func.txt`, `imports.txt` and `mutation.json` with your own toolchain (the error messages show the commands),
then `gauntlet stamp .` and `gauntlet check .`.

## Develop

```sh
git clone git@github.com:gajeshbhat/gauntlet.git && cd gauntlet
./check.sh     # ruff, pyright (strict), pytest at 100% branch coverage, then gauntlet checks itself
```

## Licence

[MIT](LICENSE).

## Credits

The idea is Robert C. Martin's: surround agents with extreme constraints and run the gauntlet instead of reading the
code ([interview with Matt Pocock](https://youtu.be/zcLPGC-tvgk), [post](https://x.com/unclebobmartin/status/2080257779395154409)).
AmazingAng's MIT-licensed [old-coder](https://github.com/amazingang/old-coder) applies it as an agent skill; we borrowed
ideas only (human-approved spec first, fail closed, negative controls, an evidence report), no code or text.
