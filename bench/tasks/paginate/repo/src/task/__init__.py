from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    start: int
    end: int
    pages: int
    has_previous: bool
    has_next: bool


def paginate(total: int, page: int, per_page: int) -> Page:
    raise NotImplementedError
