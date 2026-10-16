"""Which code a gate looks at: whole files (`path`) or line ranges (`path:lo-hi`), e.g. the changed lines."""

from dataclasses import dataclass

Entry = tuple[str, tuple[int, int] | None]


@dataclass(frozen=True)
class Scope:
    entries: tuple[Entry, ...] = ()  # empty means everything

    def contains(self, path: str, line: int) -> bool:
        if not self.entries:
            return True
        return any(_matches(path, name) and (span is None or span[0] <= line <= span[1]) for name, span in self.entries)


def _matches(path: str, name: str) -> bool:
    if name.endswith("/"):  # a directory: everything below it
        return path.startswith(name) or ("/" + name) in path
    return path == name or path.endswith("/" + name)


def _entry(item: str) -> Entry:
    name, sep, span = item.rpartition(":")
    if not sep:
        name, span = item, ""
    if not name:
        raise ValueError(f"bad scope entry {item!r}: empty path")
    if not span:
        return name, None
    if name.endswith("/"):
        raise ValueError(f"bad scope entry {item!r}: a directory takes no line range")
    lo, _, hi = span.partition("-")
    if not (lo.isdigit() and hi.isdigit() and int(lo) <= int(hi)):
        raise ValueError(f"bad scope entry {item!r}: expected path or path:lo-hi")
    return name, (int(lo), int(hi))


def parse(items: list[str]) -> Scope:
    return Scope(tuple(_entry(i) for i in items))
