"""Per-repo `gauntlet.toml`. Strict: unknown keys and wrong types are errors, never silently ignored."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gauntlet import languages
from gauntlet.errors import GauntletError

KEYS = {
    "": {"language", "src", "crap", "mutation", "layers"},
    "crap": {"max"},
    "mutation": {"min_score", "tool"},
    "layers": {"order", "roots", "forbid"},
}
RULE = re.compile(r"^(\S+) -> (\S+)(?: except (\S+(?:, \S+)*))?$")  # "A -> B" or "A -> B except C, D"


@dataclass(frozen=True)
class Rule:
    """Modules under `source` may not import anything under `target`, except what is under one of `allow`."""

    source: str
    target: str
    allow: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    language: str
    crap_max: int = 8  # raised from the human-oriented 4-5: agents handle more complexity
    mutation_min: int = 90
    layers: tuple[str, ...] = ()  # outermost first; dependencies only point inward
    src: str = "."  # where module names are rooted for the arch gate
    roots: tuple[str, ...] = ()  # several such roots (e.g. one per package); empty means just `src`
    forbid: tuple[Rule, ...] = ()  # imports banned even where the layers would allow them
    explicit: frozenset[str] = frozenset()  # sections the repo set itself ("crap", "mutation"); the rest are defaults
    mutation_tool: str = "mutmut"  # one of the language's mutation tools


def _section(path: Path, data: dict[str, Any], name: str) -> dict[str, Any]:
    table: dict[str, Any] = data.get(name, {}) if name else data
    unknown = sorted(set(table) - KEYS[name])
    if unknown:
        where = f"[{name}]" if name else "the top level"
        raise GauntletError(f"{path}: unknown key(s) {', '.join(unknown)} in {where}")
    return table


def _int(path: Path, table: dict[str, Any], key: str, default: int, lo: int, hi: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise GauntletError(f"{path}: {key} must be an integer between {lo} and {hi}")
    return value


def _text(path: Path, table: dict[str, Any], key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise GauntletError(f"{path}: {key} must be a string")
    return value


def _strings(path: Path, table: dict[str, Any], key: str, default: tuple[str, ...], label: str = "") -> tuple[str, ...]:
    value: Any = table.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        raise GauntletError(f"{path}: {label or key} must be a list of non-empty strings")
    return tuple(str(x) for x in value)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def _rules(path: Path, table: dict[str, Any]) -> tuple[Rule, ...]:
    rules: list[Rule] = []
    for text in _strings(path, table, "forbid", (), "layers.forbid"):
        m = RULE.match(text)
        if m is None:
            raise GauntletError(f"{path}: forbid rule {text!r} must look like 'A -> B' or 'A -> B except C, D'")
        rules.append(Rule(m[1], m[2], tuple(m[3].split(", ")) if m[3] else ()))
    return tuple(rules)


def load(path: Path) -> Config:
    data = tomllib.loads(path.read_text())
    top = _section(path, data, "")
    sections = {name: _section(path, data, name) for name in KEYS if name}
    language = top.get("language")
    if language is None:
        raise GauntletError(f"{path}: 'language' is required")
    try:
        tools = languages.get(language).mutation
    except ValueError as e:
        raise GauntletError(f"{path}: {e}") from None
    tool = _text(path, sections["mutation"], "tool", Config.mutation_tool)
    if tool not in tools:
        raise GauntletError(f"{path}: mutation.tool must be one of {', '.join(tools)}")
    return Config(
        language=language,
        crap_max=_int(path, sections["crap"], "max", Config.crap_max, 1, 1000),
        mutation_min=_int(path, sections["mutation"], "min_score", Config.mutation_min, 0, 100),
        mutation_tool=tool,
        layers=_strings(path, sections["layers"], "order", (), "layers.order"),
        src=_text(path, top, "src", Config.src),
        roots=_strings(path, sections["layers"], "roots", (), "layers.roots"),
        forbid=_rules(path, sections["layers"]),
        explicit=frozenset(n for n, key in (("crap", "max"), ("mutation", "min_score")) if key in sections[n]),
    )
