# gauntlet

Quality gates and an ephemeral-agent loop for code written by AI agents: do not read the code, make it run the gauntlet.
Python and Go. Design and rationale: [PROPOSAL.md](PROPOSAL.md). Threat model: [SECURITY.md](SECURITY.md).

    gauntlet run ROOT        # in a Workshop sandbox: tests+coverage, mutation; then every gate, stamped
    gauntlet check ROOT      # arch (if layers are set) + clean + exclusions, on existing artifacts
    gauntlet arch|clean|harden|exclusions|spec ROOT
    gauntlet diagram ROOT    # Mermaid of the layer graph, violations in red
    gauntlet stamp ROOT      # bind existing artifacts to the current source
    gauntlet pin ROOT        # record gauntlet.toml's hash in your policy
    gauntlet loop ROOT --requirement "..."   # Specifier writes a spec for you to approve (exit 3)
    gauntlet loop ROOT --spec spec.feature   # Coder + Fixer rounds in a workspace copy; you get loop.patch + EVIDENCE.md

Options: `--only PATH[:LO-HI]|DIR/` scope, `--artifacts`, `--source`, `--policy`, `--json`, `--report`, `--out`.
Exit codes: 0 pass, 1 a gate failed, 2 error or refused input, 3 spec awaiting approval.

## Gates
| Gate | Checks | Python | Go |
|---|---|---|---|
| clean | CRAP score per function (default max 8) | radon + coverage.py | gocyclo + `go tool cover` |
| arch | imports only point inward through `[layers]` (longest prefix wins) | `ast` | `go list` |
| harden | mutation score (default min 90) | mutmut | gremlins |
| exclusions | budget of `pragma: no mutate/cover`, `nolint`, `nosec`; coverage/mutmut excludes | yes | yes |
| spec | Gherkin is well formed; every scenario has When/Then and `@test(file::name)` that exists | yes | yes |

Every gate fails closed: nothing evaluated is an error, never a pass.

## Rules the repo cannot weaken
`~/.config/gauntlet/policy.toml` (yours, outside the repo): `crap_ceiling`, `mutation_floor`, `max_exclusions`,
`allow_config_excludes`, `allow_unstamped`, `require_pin`, pins, and the agent (`agent_command`, `agent_env`,
`agent_timeout`, `max_rounds`). `gauntlet.toml` may only tighten them. Unknown keys are errors.

    # gauntlet.toml
    language = "python"            # or "go"
    src = "src"
    [layers]
    order = ["app.web", "app.service", "app.domain"]   # outermost first

Go repos set `[go]` `packages`, `mutation_dir`, `mutate_only`.

## Develop

    ./check.sh    # ruff, pyright strict, pytest (100% branch coverage), then gauntlet on itself

## Credits
Inspired by Robert C. Martin's "run the gauntlet" approach (interview with Matt Pocock: https://youtu.be/zcLPGC-tvgk)
and by AmazingAng's MIT-licensed [old-coder](https://github.com/amazingang/old-coder). Ideas only; no code or text copied.
