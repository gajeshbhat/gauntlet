# Task: parse a duration

Implement `task.parse_duration(text: str) -> int` in `src/task/__init__.py`, returning the number of seconds, and
write tests in `tests/`.

- A duration is one or more `<digits><unit>` parts with no spaces, for example `1h30m`, `45s`, `2d`, `1d2h3m4s`.
- Units are `d` (86400 s), `h` (3600 s), `m` (60 s) and `s` (1 s), lowercase only.
- Units appear in that order (largest first) and each at most once.
- Anything else raises `ValueError`: an empty string, an unknown or uppercase unit, a number without a unit, a unit
  without a number, spaces, units out of order or repeated.
