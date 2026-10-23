# Task: split a CSV line

Implement `task.split_line(line: str) -> list[str]` in `src/task/__init__.py`, and write tests in `tests/`. Do not use
the `csv` module.

- Fields are separated by commas. An empty line is one empty field: `[""]`; `a,` is `["a", ""]`.
- A field that starts with `"` is quoted: it runs to the next `"` that is not doubled, may contain commas, and `""`
  inside it stands for one `"`. The closing quote must be followed by a comma or the end of the line.
- Spaces are kept as they are; a quote that does not start a field is an ordinary character.
- An unclosed quote, or text after a closing quote, raises `ValueError` naming the position, for example
  `unclosed quote at 4`, `text after closing quote at 3`.
