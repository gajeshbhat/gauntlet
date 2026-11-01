"""Every supported language is one row. Python only for now; the others live at tag v0.1-multilang."""

from dataclasses import dataclass
from pathlib import Path

from gauntlet.errors import GauntletError


@dataclass(frozen=True)
class Language:
    suffixes: tuple[str, ...]  # source files
    markers: tuple[str, ...]  # files (globs) whose presence says "this project uses the language" (for `init`)
    tests: str  # regex for test files: the clean gate does not hold them to the CRAP limit
    pragma: str  # regex for the comments that exclude code from the gates
    coverage_file: str  # the artifact the clean gate reads ...
    coverage_format: str  # ... and its format (a key of linecov.PARSERS)
    sdk: str  # the Canonical Workshop SDK
    image: str  # the default Docker image (the policy can override it per language)
    artifacts: tuple[str, ...]  # every file the gates read; `stamp` binds these


TABLE: dict[str, Language] = {
    "python": Language(
        suffixes=(".py",),
        markers=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        tests=r"^(tests?/|conftest\.py$)",  # only the top-level test dir: a name inside src/ cannot opt out
        pragma=r"#\s*(?:pragma:\s*no\s+(?:mutate|cover)|nosec)\b",
        coverage_file="coverage.json",
        coverage_format="coveragepy",
        sdk="uv",
        image="ghcr.io/astral-sh/uv:python3.12-bookworm",
        artifacts=("coverage.json", "mutmut-results.txt"),
    ),
}
NAMES = tuple(TABLE)


def get(name: str) -> Language:
    if name not in TABLE:
        raise GauntletError(f"unsupported language {name!r}, expected one of {', '.join(NAMES)}")
    return TABLE[name]


def detect(root: Path) -> list[str]:
    """The languages whose marker files exist in `root`, in table order."""
    return [name for name, row in TABLE.items() if any(next(root.glob(m), None) for m in row.markers)]
