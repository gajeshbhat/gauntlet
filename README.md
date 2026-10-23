# gauntlet

**Don't read the code an AI agent wrote. Make it run a gauntlet, and read the evidence.**

gauntlet runs tests, coverage and mutation testing in a sandbox, then fails loudly when code is too complex for its
tests, when tests let planted bugs survive, or when code is hidden from the checks. It works on Python, Go,
JavaScript/TypeScript, C#, Java, Rust, C/C++ and Dart projects, with no code changes.

```sh
uv tool install git+https://github.com/gajeshbhat/gauntlet
cd your-project
gauntlet init .
gauntlet run . --report EVIDENCE.md
```

```mermaid
flowchart LR
    repo["Your repository"] --> copy["Private copy"]
    subgraph box["Sandbox: Workshop or Docker"]
        copy --> tests["Tests with coverage"]
        tests --> mutants["Mutation testing"]
    end
    mutants --> stamp["Artifacts, stamped<br/>to the source"]
    stamp --> gates["Gates<br/>clean · harden<br/>arch · exclusions"]
    policy["Your policy<br/>outside the repo"] -.-> gates
    gates -->|pass| pass["Exit 0<br/>EVIDENCE.md"]
    gates -->|fail| fail["Exit 1<br/>file:line findings"]

    classDef default fill:#ffffff,stroke:#9ca3af,color:#1f2937
    classDef you fill:#fff4d6,stroke:#c99a00,color:#3d2e00
    classDef good fill:#e3f6e8,stroke:#2f9e57,color:#0f3d1f
    classDef bad fill:#fde7e7,stroke:#d64545,color:#4d0f0f
    class repo,policy you
    class pass good
    class fail bad
    style box fill:#eef4ff,stroke:#5b8def,color:#1b2f5c
```

`run` needs [Canonical Workshop](https://snapcraft.io/workshop) or Docker. In Claude Code 2.1.275 or later:
`/plugin install gauntlet --marketplace gajeshbhat/gauntlet`, then `/gauntlet`.

## Documentation

- [Tutorial](docs/tutorial.md): your first gauntlet run, start to finish.
- [How-to guides](docs/how-to.md): CI, the agent loop, your own toolchain, Docker, policies.
- [Reference](docs/reference.md): commands, exit codes, gates, languages, `gauntlet.toml`, `policy.toml`.
- [Explanation](docs/explanation.md): why the gates fail closed, and how results are bound to the source.
- [Security model](SECURITY.md): what gauntlet does and does not protect against.

## Develop

```sh
./check.sh     # ruff, pyright (strict), pytest at 100% branch coverage, then gauntlet checks itself
```

[MIT](LICENSE). The idea is Robert C. Martin's; see [credits](docs/explanation.md#credits).
