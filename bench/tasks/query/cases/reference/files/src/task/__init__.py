import re

ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")


def _decode(text: str, offset: int) -> str:
    text = text.replace("+", " ")
    out = bytearray()
    i = 0
    while i < len(text):
        if text[i] != "%":
            out += text[i].encode()
            i += 1
            continue
        match = ESCAPE.match(text, i)
        if not match:
            raise ValueError(f"bad escape at {offset + i}")
        out.append(int(match.group(1), 16))
        i = match.end()
    return out.decode("utf-8")


def parse_query(query: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    offset = 0
    for pair in query.split("&"):
        if pair:
            key, sep, value = pair.partition("=")
            decoded = _decode(key, offset)
            result.setdefault(decoded, []).append(_decode(value, offset + len(key) + len(sep)))
        offset += len(pair) + 1
    return result
