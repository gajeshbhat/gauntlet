"""Reading files named by untrusted input without leaving the project or exhausting memory."""

import os
from pathlib import Path

from gauntlet.errors import GauntletError

MAX_SOURCE_BYTES = 5_000_000
MAX_ARTIFACT_BYTES = 64_000_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox"}  # never project source, at any depth
SKIP_TOP = {
    "build",
    "target",
    "dist",
    "vendor",
    "mutants",
    ".gauntlet",
    ".gauntlet-out",
    ".gauntlet-loop",
}  # top level only


def inside(root: Path, rel: str) -> Path:
    """`root / rel` with symlinks resolved; refuses anything that ends up outside `root`."""
    base = root.resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        raise GauntletError(f"{rel!r} escapes the project root")
    return path


def read_text(path: Path, limit: int) -> str:
    size = path.stat().st_size
    if size > limit:
        raise GauntletError(f"{path} is {size} bytes, over the {limit} byte limit")
    try:
        return path.read_text()
    except UnicodeDecodeError:
        raise GauntletError(f"{path} is not valid UTF-8") from None


def source_files(root: Path, suffixes: tuple[str, ...]) -> list[str]:
    """Project-relative paths of the files ending in one of `suffixes`, minus vendored and top-level build dirs."""
    found: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        top = Path(dirpath) == root
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (top and d in SKIP_TOP))
        found += [(Path(dirpath) / n).relative_to(root).as_posix() for n in sorted(names) if n.endswith(suffixes)]
    return found


def read_artifact(root: Path, name: str, how: str) -> str:
    """A gate input produced earlier (`gauntlet run` or your own toolchain); a missing one says how to make it."""
    path = root / name
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; produce it with: {how}")
    return read_text(path, MAX_ARTIFACT_BYTES)
