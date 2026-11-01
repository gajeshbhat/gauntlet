"""Things that make code invisible to the gates: exclusion comments and exclusion settings in the repo's own config."""

import configparser
import io
import re
import tokenize
import tomllib
from pathlib import Path
from typing import Any

from gauntlet import languages
from gauntlet.errors import GauntletError
from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text, source_files
from gauntlet.scope import Scope


def _python_comments(rel: str, text: str) -> list[tuple[int, str]]:
    """Real comments only: pragma text inside string literals does not count."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        return [(t.start[0], t.string) for t in tokens if t.type == tokenize.COMMENT]
    except (tokenize.TokenError, SyntaxError):
        raise GauntletError(f"cannot analyse {rel}") from None


def pragmas(root: Path, language: str, scope: Scope) -> list[str]:
    row = languages.get(language)
    pattern = re.compile(row.pragma)
    out: list[str] = []
    for rel in source_files(root, row.suffixes):
        text = read_text(inside(root, rel), MAX_SOURCE_BYTES)
        lines = text.splitlines()
        out += [
            f"{rel}:{n}: {lines[n - 1].strip()}"
            for n, comment in _python_comments(rel, text)
            if pattern.search(comment) and scope.contains(rel, n)
        ]
    return out


def _pyproject(root: Path) -> list[str]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        data: dict[str, Any] = tomllib.loads(read_text(path, MAX_SOURCE_BYTES))
    except tomllib.TOMLDecodeError:
        raise GauntletError("cannot read pyproject.toml") from None
    tool: dict[str, Any] = data.get("tool", {})
    coverage: dict[str, Any] = tool.get("coverage", {})
    wanted = [(_label(sec, key), coverage.get(sec, {}).get(key, [])) for sec, key in COVERAGE_KEYS]
    wanted.append(("mutmut do_not_mutate", tool.get("mutmut", {}).get("do_not_mutate", [])))
    return [f"pyproject.toml: {label} {item}" for label, items in wanted for item in items]


COVERAGE_KEYS = (
    ("run", "omit"),
    ("run", "include"),
    ("report", "omit"),
    ("report", "include"),
    ("report", "exclude_lines"),
    ("report", "exclude_also"),
)  # coverage's `source` is not listed: the runner passes --cov=<src>, which overrides it


SHORT_LABELS = {("run", "omit"), ("report", "exclude_lines"), ("report", "exclude_also")}


def _label(section: str, key: str) -> str:
    """`coverage omit` for the common keys, `coverage report omit` / `coverage run include` where it is ambiguous."""
    return f"coverage {key}" if (section, key) in SHORT_LABELS else f"coverage {section} {key}"


def _ini(root: Path, name: str, coverage_prefix: str, mutmut_section: str | None) -> list[str]:
    path = root / name
    if not path.is_file():
        return []
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(read_text(path, MAX_SOURCE_BYTES))
    wanted = [(f"{coverage_prefix}{sec}", key, _label(sec, key)) for sec, key in COVERAGE_KEYS]
    if mutmut_section:
        wanted.append((mutmut_section, "do_not_mutate", "mutmut do_not_mutate"))
    return [
        f"{name}: {label} {line.strip()}"
        for section, key, label in wanted
        for line in parser.get(section, key, fallback="").splitlines()
        if line.strip()
    ]


def config_excludes(root: Path) -> list[str]:
    return (
        _pyproject(root)
        + _ini(root, ".coveragerc", "", None)
        + _ini(root, "setup.cfg", "coverage:", "mutmut")
        + _ini(root, "tox.ini", "coverage:", None)
    )
