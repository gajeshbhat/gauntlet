# Task: compare semantic versions

Implement `task.compare(a: str, b: str) -> int` in `src/task/__init__.py`, returning -1, 0 or 1 as `a` is lower than,
equal to or higher than `b` under Semantic Versioning 2.0.0, and write tests in `tests/`.

- A version is `MAJOR.MINOR.PATCH`, optionally followed by `-PRERELEASE` and `+BUILD`. The three numbers are
  non-negative integers without leading zeros.
- Compare MAJOR, MINOR and PATCH numerically.
- A pre-release version is lower than the same version without one: `1.0.0-alpha < 1.0.0`.
- Pre-releases compare identifier by identifier (split on `.`): numeric identifiers compare as numbers, others as
  ASCII text, a numeric identifier is lower than a non-numeric one, and a shorter list is lower when all its
  identifiers are equal: `alpha < alpha.1 < alpha.beta < beta < beta.2 < beta.11 < rc.1`.
- Build metadata is ignored: `1.0.0+a` equals `1.0.0+b`.
- An invalid version raises `ValueError` naming it, for example `invalid version: '1.2'`.
