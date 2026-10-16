"""Things that make code invisible to the gates: exclusion comments and exclusion settings in the repo's own config."""

import configparser
import io
import os
import re
import tokenize
import tomllib
from pathlib import Path
from typing import Any

from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text
from gauntlet.scope import Scope

PRAGMA = re.compile(r"(?:#|//)\s*(?:pragma:\s*no\s+(?:mutate|cover)|nolint|nosec)\b")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "vendor", "mutants", "__pycache__", ".tox"}
SUFFIX = {"python": ".py", "go": ".go"}


def _files(root: Path, suffix: str) -> list[str]:
    found: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        found += [str((Path(dirpath) / n).relative_to(root)) for n in sorted(names) if n.endswith(suffix)]
    return found


def _python_comments(rel: str, text: str) -> list[tuple[int, str]]:
    """Real comments only: pragma text inside string literals does not count."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        return [(t.start[0], t.string) for t in tokens if t.type == tokenize.COMMENT]
    except (tokenize.TokenError, SyntaxError):
        raise ValueError(f"cannot analyse {rel}") from None


def _comments(rel: str, text: str, language: str) -> list[tuple[int, str]]:
    if language == "python":
        return _python_comments(rel, text)
    return list(enumerate(text.splitlines(), 1))


def pragmas(root: Path, language: str, scope: Scope, max_bytes: int = MAX_SOURCE_BYTES) -> list[str]:
    out: list[str] = []
    for rel in _files(root, SUFFIX[language]):
        text = read_text(inside(root, rel), max_bytes)
        lines = text.splitlines()
        out += [
            f"{rel}:{n}: {lines[n - 1].strip()}"
            for n, comment in _comments(rel, text, language)
            if PRAGMA.search(comment) and scope.contains(rel, n)
        ]
    return out


def _pyproject(root: Path) -> list[str]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        data: dict[str, Any] = tomllib.loads(read_text(path, MAX_SOURCE_BYTES))
    except tomllib.TOMLDecodeError:
        raise ValueError("cannot read pyproject.toml") from None
    tool: dict[str, Any] = data.get("tool", {})
    coverage: dict[str, Any] = tool.get("coverage", {})
    wanted = [
        ("coverage omit", coverage.get("run", {}).get("omit", [])),
        ("coverage exclude_lines", coverage.get("report", {}).get("exclude_lines", [])),
        ("coverage exclude_also", coverage.get("report", {}).get("exclude_also", [])),
        ("mutmut do_not_mutate", tool.get("mutmut", {}).get("do_not_mutate", [])),
    ]
    return [f"pyproject.toml: {label} {item}" for label, items in wanted for item in items]


def _coveragerc(root: Path) -> list[str]:
    path = root / ".coveragerc"
    if not path.is_file():
        return []
    parser = configparser.ConfigParser()
    parser.read_string(read_text(path, MAX_SOURCE_BYTES))
    omit = parser.get("run", "omit", fallback="")
    return [f".coveragerc: coverage omit {line.strip()}" for line in omit.splitlines() if line.strip()]


def config_excludes(root: Path) -> list[str]:
    return _pyproject(root) + _coveragerc(root)
