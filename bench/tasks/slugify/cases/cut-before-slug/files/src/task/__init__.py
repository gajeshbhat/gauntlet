import re
import unicodedata

WORD = re.compile(r"[a-z0-9]+")


def slugify(text: str, max_length: int | None = None) -> str:
    if max_length is not None and max_length < 1:
        raise ValueError("max_length must be at least 1")
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if c.isascii())
    if max_length is not None:
        plain = plain[:max_length]
    return "-".join(WORD.findall(plain.lower()))
