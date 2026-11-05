# Contributing

```sh
git clone https://github.com/gajeshbhat/gauntlet && cd gauntlet
./check.sh      # ruff, pyright (strict), tests at 100% branch coverage, then gauntlet checks itself
```

`./check.sh` must pass. CI runs the same script, including the mutation gate on gauntlet's own code.

- Open a pull request from a branch; `main` is protected. Use [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat|fix|refactor|docs|build|test|ci: ...`).
- Write the test first. Do not lower a threshold, widen the exclusion budget or delete a test that guards behaviour; if a
  test has to change, say in the PR what it pinned and what replaces it.
- Keep it lean: prefer deleting code to adding it. Read [docs/architecture.md](docs/architecture.md) first.
- Security issues: see [SECURITY.md](SECURITY.md); do not open a public issue.
