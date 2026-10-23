# Task: merge intervals

Implement `task.merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]` in
`src/task/__init__.py`, and write tests in `tests/`.

- Each interval is `(start, end)` with `start <= end`; `start == end` is a valid, empty-length interval.
- Return the intervals sorted by start, with overlapping or touching intervals merged: `(1, 3)` and `(3, 5)` touch
  and merge into `(1, 5)`. `(1, 2)` and `(3, 4)` do not touch.
- An interval with `start > end` raises `ValueError` naming it, for example `start after end: (3, 1)`.
- Do not change the list you are given.
