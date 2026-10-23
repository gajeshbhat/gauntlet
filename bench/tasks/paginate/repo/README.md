# Task: paginate

Implement `task.paginate(total: int, page: int, per_page: int) -> Page` in `src/task/__init__.py`, and write tests in
`tests/`. `Page` is a frozen dataclass with `start`, `end`, `pages`, `has_previous` and `has_next`.

- `total` items are shown `per_page` at a time; pages are numbered from 1.
- `pages` is the number of pages, at least 1 (an empty list still has one, empty, page).
- `start` and `end` are the slice bounds of the page's items: `items[start:end]`. On an empty list both are 0.
- `has_previous` is true from page 2 on; `has_next` is true unless the page is the last one.
- `total < 0`, `per_page < 1`, `page < 1` or `page > pages` raise `ValueError` naming the bad argument, for example
  `page 4 is out of range 1-3`.
