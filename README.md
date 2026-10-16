# gauntlet

Agent-agnostic quality gates plus an ephemeral-agent loop. Design: [PROPOSAL.md](PROPOSAL.md).

    gauntlet arch [ROOT]     # layer boundaries from gauntlet.toml
    gauntlet clean [ROOT]    # CRAP score per function (needs coverage.json)
    gauntlet harden [ROOT]   # mutation score via mutmut
    gauntlet check [ROOT]    # arch + clean

Python targets only so far; Go is next. Exit codes: 0 pass, 1 gate failed, 2 usage/config error.

    ./check.sh    # ruff, pyright (strict), pytest with 100% branch coverage, then gauntlet on itself
