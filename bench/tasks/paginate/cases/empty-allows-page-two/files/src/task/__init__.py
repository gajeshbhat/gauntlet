from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    start: int
    end: int
    pages: int
    has_previous: bool
    has_next: bool


def paginate(total: int, page: int, per_page: int) -> Page:
    if total < 0:
        raise ValueError(f"total {total} is negative")
    if per_page < 1:
        raise ValueError(f"per_page {per_page} is below 1")
    pages = max(1, -(-total // per_page))
    if page < 1 or (total and page > pages):
        raise ValueError(f"page {page} is out of range 1-{pages}")
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    return Page(start, end, pages, page > 1, page < pages)
