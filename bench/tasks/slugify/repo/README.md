# Task: make a URL slug

Implement `task.slugify(text: str, max_length: int | None = None) -> str` in `src/task/__init__.py`, and write tests
in `tests/`.

- Accented letters lose their accents (`é` becomes `e`); other non-ASCII characters are dropped.
- The result is lowercase; every run of characters other than `a-z` and `0-9` becomes one `-`.
- No `-` at the start or end.
- With `max_length`, cut the slug to at most that many characters, then remove any `-` left at the end.
- `max_length` below 1 raises `ValueError("max_length must be at least 1")`.
