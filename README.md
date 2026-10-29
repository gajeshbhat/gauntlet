# gauntlet

**Don't read the code an AI agent wrote. Make it run a gauntlet, and read the evidence.**

gauntlet runs tests, coverage and mutation testing in a sandbox. It fails when code is too complex for its tests, when
tests let planted bugs survive, or when code is hidden from the checks. Supports Python, Go, JavaScript/TypeScript, C#,
Java, Rust, C/C++ and Dart.

## Quickstart

You need `git`, [`uv`](https://docs.astral.sh/uv/) and a sandbox: [Workshop](https://snapcraft.io/workshop)
(`sudo snap install workshop --classic`) on Linux, or Docker or Podman.

```sh
uv tool install git+https://github.com/gajeshbhat/gauntlet
cd your-project                        # a git repository
gauntlet init .                        # detect the language, write gauntlet.toml
gauntlet run . --report EVIDENCE.md    # exit 0: every gate passed
```

In Claude Code 2.1.275 or later: `/plugin install gauntlet --marketplace gajeshbhat/gauntlet`, then `/gauntlet`.

## Documentation

- [Tutorial](docs/tutorial.md)
- [How-to guides](docs/how-to.md)
- [Reference](docs/reference.md)
- [Explanation](docs/explanation.md)
- [Security model](SECURITY.md)

## Develop

```sh
./check.sh     # ruff, pyright (strict), pytest at 100% branch coverage, then gauntlet checks itself
```

## Credits

The idea comes from Robert C. Martin: surround the agent with strict constraints and make its work run a gauntlet,
instead of reading its code. He describes it in an [interview with Matt Pocock](https://youtu.be/zcLPGC-tvgk) and in
[this post](https://x.com/unclebobmartin/status/2080257779395154409).

[old-coder](https://github.com/amazingang/old-coder) by AmazingAng applies the same idea as an agent skill. gauntlet
borrows some of its ideas (a spec a person approves first, gates that fail closed, negative controls, an evidence
report) but none of its code or text.

## License

gauntlet is released under the [MIT License](LICENSE). Copyright © 2026 Gajesh Bhat.
