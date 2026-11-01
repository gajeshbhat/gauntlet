"""Line coverage as one shape ({file: {line: hit count}}), read by the language plugin; here, matching its paths.

Only executable lines appear in a file's map; a line that is absent is not code that could run.
"""

from gauntlet.errors import GauntletError
from gauntlet.plugin import Language, Lines
from gauntlet.safefs import SKIP_DIRS
from gauntlet.sandbox import PROJECT_DIR


def parse(language: Language, text: str) -> Lines:
    try:
        return language.read_coverage(text)
    except (KeyError, TypeError, AttributeError, ValueError):  # json.JSONDecodeError is a ValueError
        raise GauntletError(f"cannot read {language.coverage_format} report") from None


def _clean_key(key: str) -> tuple[str, bool]:
    """The report path made project-relative, and whether it came from a host root outside the container."""
    foreign_root = key.startswith("/") and not key.startswith(f"{PROJECT_DIR}/")
    key = key.removeprefix(f"{PROJECT_DIR}/").lstrip("/")
    if ".." in key.split("/"):
        raise GauntletError(f"{key!r} escapes the project root")
    return key, foreign_root


def _longest_under_prefix(key: str, files: list[str]) -> str | None:
    """The project file that ends `key` when the report put extra leading directories before it."""
    if any(part in SKIP_DIRS for part in key.split("/")):  # never credit a dependency's coverage to our file
        return None
    return max((f for f in files if key.endswith("/" + f)), key=len, default=None)


def locate(key: str, files: list[str]) -> str | None:
    """The source file a coverage path names. Reports are relative to different roots, so match by path suffix."""
    key, foreign_root = _clean_key(key)
    if key in files:
        return key
    shorter = [f for f in files if f.endswith("/" + key)]
    if len(shorter) > 1:
        raise GauntletError(f"coverage path {key!r} matches more than one file: {', '.join(sorted(shorter))}")
    if shorter:
        return shorter[0]
    return _longest_under_prefix(key, files) if foreign_root else None
