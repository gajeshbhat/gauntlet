# Task: parse a query string

Implement `task.parse_query(query: str) -> dict[str, list[str]]` in `src/task/__init__.py`, and write tests in
`tests/`. Do not use `urllib`.

- Pairs are separated by `&`; empty pairs (`a=1&&b=2`) are skipped.
- A pair splits at its first `=` into key and value; a pair without `=` has the value `""`.
- In keys and values, `+` means a space and `%XX` (two hex digits, either case) is that byte; decoded bytes are UTF-8.
  Decode after splitting, so `%26` and `%3D` are a literal `&` and `=`.
- Keys keep every value, in order: `a=1&a=2` gives `{"a": ["1", "2"]}`.
- A `%` not followed by two hex digits raises `ValueError` naming its position, for example `bad escape at 3`.
