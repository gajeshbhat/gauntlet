# Task: wrap text

Implement `task.wrap(text: str, width: int) -> list[str]` in `src/task/__init__.py`, and write tests in `tests/`.
Do not use `textwrap`.

- Words are separated by any run of whitespace; lines hold as many whole words as fit in `width` characters,
  separated by single spaces.
- A word longer than `width` is split into pieces of exactly `width` characters (the last piece may be shorter), each
  piece starting a new line; text after the last piece continues on that line if it fits.
- Text that is empty or only whitespace gives `[]`.
- `width < 1` raises `ValueError("width must be at least 1")`.
