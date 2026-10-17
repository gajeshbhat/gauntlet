"""Every supported language is one row. Adding a language starts here."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Language:
    suffixes: tuple[str, ...]  # source files
    markers: tuple[str, ...]  # files whose presence says "this project uses the language" (for `init`)
    pragma: str  # regex for the comments that exclude code from the gates
    coverage_file: str  # the artifact the clean gate reads ...
    coverage_format: str  # ... and its format (a key of linecov.PARSERS)
    sdk: str  # the Canonical Workshop SDK
    image: str  # the default Docker image (the policy can override it per language)


TABLE: dict[str, Language] = {
    "python": Language(
        suffixes=(".py",),
        markers=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        pragma=r"#\s*(?:pragma:\s*no\s+(?:mutate|cover)|nosec)\b",
        coverage_file="coverage.json",
        coverage_format="coveragepy",
        sdk="uv",
        image="ghcr.io/astral-sh/uv:python3.12-bookworm",
    ),
    "go": Language(
        suffixes=(".go",),
        markers=("go.mod",),
        pragma=r"//\s*nolint\b",
        coverage_file="cover.out",
        coverage_format="gocover",
        sdk="go",
        image="golang:1.27",
    ),
}
NAMES = tuple(TABLE)


def get(name: str) -> Language:
    if name not in TABLE:
        raise ValueError(f"unsupported language {name!r}, expected one of {', '.join(NAMES)}")
    return TABLE[name]


def detect(root: Path) -> list[str]:
    """The languages whose marker files exist in `root`, in table order."""
    return [name for name, row in TABLE.items() if any((root / m).exists() for m in row.markers)]
