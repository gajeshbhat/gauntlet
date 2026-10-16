"""Reading files named by untrusted input without leaving the project or exhausting memory."""

from pathlib import Path

MAX_SOURCE_BYTES = 5_000_000
MAX_ARTIFACT_BYTES = 64_000_000


def inside(root: Path, rel: str) -> Path:
    """`root / rel` with symlinks resolved; refuses anything that ends up outside `root`."""
    base = root.resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"{rel!r} escapes the project root")
    return path


def read_text(path: Path, limit: int) -> str:
    size = path.stat().st_size
    if size > limit:
        raise ValueError(f"{path} is {size} bytes, over the {limit} byte limit")
    try:
        return path.read_text()
    except UnicodeDecodeError:
        raise ValueError(f"{path} is not valid UTF-8") from None
