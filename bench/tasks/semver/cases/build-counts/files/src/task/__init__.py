import re

VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.+-]+))?(?:\+[0-9A-Za-z.-]+)?")


def _parse(text: str) -> tuple[tuple[int, int, int], list[str]]:
    match = VERSION.fullmatch(text)
    if not match:
        raise ValueError(f"invalid version: {text!r}")
    numbers = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    pre = match.group(4).split(".") if match.group(4) else []
    return numbers, pre


def _identifier(part: str) -> tuple[bool, int | str]:
    numeric = part.isdigit()
    return (not numeric, int(part) if numeric else part)


def _sign(x: object, y: object) -> int:
    return (x > y) - (x < y)  # type: ignore[operator]


def compare(a: str, b: str) -> int:
    (numbers_a, pre_a), (numbers_b, pre_b) = _parse(a), _parse(b)
    if numbers_a != numbers_b:
        return _sign(numbers_a, numbers_b)
    if not pre_a or not pre_b:
        return _sign(not pre_a, not pre_b)
    return _sign([_identifier(p) for p in pre_a], [_identifier(p) for p in pre_b])
