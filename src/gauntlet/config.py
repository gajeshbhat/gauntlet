"""Per-repo `gauntlet.toml`. Strict: unknown keys and wrong types are errors, never silently ignored."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gauntlet import languages
from gauntlet.errors import GauntletError

KEYS = {
    "": {"language", "src", "crap", "mutation", "layers", "go"},
    "crap": {"max"},
    "mutation": {"min_score"},
    "layers": {"order"},
    "go": {"mutation_dir", "packages", "mutate_only"},
}


@dataclass(frozen=True)
class Config:
    language: str
    crap_max: int = 8  # raised from the human-oriented 4-5: agents handle more complexity
    mutation_min: int = 90
    layers: tuple[str, ...] = ()  # outermost first; dependencies only point inward
    src: str = "."  # where module names are rooted for the arch gate
    mutation_dir: str = ""  # Go: directory gremlins ran on; its file names are relative to it
    packages: tuple[str, ...] = ("./...",)  # Go: package patterns the sandbox tests and lists
    mutate_only: tuple[str, ...] = ()  # Go: files (relative to mutation_dir) to mutate; empty means all
    explicit: frozenset[str] = frozenset()  # sections the repo set itself ("crap", "mutation"); the rest are defaults


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


def _layers(path: Path, table: dict[str, Any]) -> tuple[str, ...]:
    order: Any = table.get("order", [])
    items: list[Any] = list(order) if isinstance(order, list) else []  # pyright: ignore[reportUnknownArgumentType]
    if not isinstance(order, list) or not all(isinstance(x, str) and x for x in items):
        raise GauntletError(f"{path}: layers.order must be a list of non-empty strings")
    return tuple(str(x) for x in items)


def _strings(path: Path, table: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value: Any = table.get(key, list(default))
    items: list[Any] = list(value) if isinstance(value, list) else []  # pyright: ignore[reportUnknownArgumentType]
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in items):
        raise GauntletError(f"{path}: {key} must be a list of non-empty strings")
    return tuple(str(x) for x in items)


def load(path: Path) -> Config:
    data = tomllib.loads(path.read_text())
    top = _section(path, data, "")
    sections = {name: _section(path, data, name) for name in KEYS if name}
    language = top.get("language")
    if language is None:
        raise GauntletError(f"{path}: 'language' is required")
    try:
        languages.get(language)
    except ValueError as e:
        raise GauntletError(f"{path}: {e}") from None
    return Config(
        language=language,
        crap_max=_int(path, sections["crap"], "max", Config.crap_max, 1, 1000),
        mutation_min=_int(path, sections["mutation"], "min_score", Config.mutation_min, 0, 100),
        layers=_layers(path, sections["layers"]),
        src=_text(path, top, "src", Config.src),
        mutation_dir=_text(path, sections["go"], "mutation_dir", Config.mutation_dir),
        packages=_strings(path, sections["go"], "packages", Config.packages),
        mutate_only=_strings(path, sections["go"], "mutate_only", Config.mutate_only),
        explicit=frozenset(n for n, key in (("crap", "max"), ("mutation", "min_score")) if key in sections[n]),
    )
