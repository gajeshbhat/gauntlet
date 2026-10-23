"""Things that make code invisible to the gates: exclusion comments and exclusion settings in the repo's own config."""

import configparser
import fnmatch
import io
import os
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


def _comments(rel: str, text: str, language: str) -> list[tuple[int, str]]:
    if language == "python":
        return _python_comments(rel, text)
    return list(enumerate(text.splitlines(), 1))


def pragmas(root: Path, language: str, scope: Scope, max_bytes: int = MAX_SOURCE_BYTES) -> list[str]:
    row = languages.get(language)
    pattern = re.compile(row.pragma)
    out: list[str] = []
    for rel in source_files(root, row.suffixes):
        text = read_text(inside(root, rel), max_bytes)
        lines = text.splitlines()
        out += [
            f"{rel}:{n}: {lines[n - 1].strip()}"
            for n, comment in _comments(rel, text, language)
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


CONFIG_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox"}  # not build/: repos keep settings there


def _config_files(root: Path, glob: str) -> list[str]:
    """Project-relative paths whose name or path matches `glob`, outside vendored directories."""
    found: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in CONFIG_SKIP)
        rels = [(Path(dirpath) / n).relative_to(root).as_posix() for n in sorted(names)]
        found += [r for r in rels if fnmatch.fnmatch(r, glob) or fnmatch.fnmatch(r, f"*/{glob}")]
    return found


def config_hints(root: Path, language: str, max_bytes: int = MAX_SOURCE_BYTES) -> list[str]:
    """Build settings of the project that can hide code from the language's coverage tool (the pyproject part for
    Python lives in `config_excludes`). A glob with no pattern flags the file's existence."""
    out: list[str] = []
    for glob, pattern in languages.get(language).config_scan:
        for rel in _config_files(root, glob):
            if not pattern:
                out.append(f"{rel}: coverage-affecting settings file")
                continue
            lines = read_text(inside(root, rel), max_bytes).splitlines()
            out += [f"{rel}:{n}: {line.strip()}" for n, line in enumerate(lines, 1) if re.search(pattern, line)]
    return out
