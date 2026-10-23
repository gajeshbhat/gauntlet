import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
ORDER = list(UNITS)
PART = re.compile(r"(\d+)([dhms])")


def parse_duration(text: str) -> int:
    text = text.replace(" ", "")
    if not text:
        raise ValueError("empty duration")
    total, position = 0, 0
    last: int | None = None
    for match in PART.finditer(text):
        if match.start() != position:
            raise ValueError(f"unexpected text at {position}")
        rank = ORDER.index(match.group(2))
        if last is not None and rank <= last:
            raise ValueError("units out of order or repeated")
        total += int(match.group(1)) * UNITS[match.group(2)]
        position, last = match.end(), rank
    if position != len(text):
        raise ValueError(f"unexpected text at {position}")
    return total
