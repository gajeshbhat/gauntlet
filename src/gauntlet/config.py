"""Per-repo `gauntlet.toml`."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

LANGUAGES = ("python", "go")


@dataclass(frozen=True)
class Config:
    language: str
    crap_max: int = 8  # raised from the human-oriented 4-5: agents handle more complexity
    mutation_min: int = 90
    layers: tuple[str, ...] = ()  # outermost first; dependencies only point inward


def load(path: Path) -> Config:
    data = tomllib.loads(path.read_text())
    language = data.get("language")
    if language is None:
        raise ValueError(f"{path}: 'language' is required")
    if language not in LANGUAGES:
        raise ValueError(f"{path}: unsupported language {language!r}, expected one of {LANGUAGES}")
    return Config(
        language=language,
        crap_max=data.get("crap", {}).get("max", Config.crap_max),
        mutation_min=data.get("mutation", {}).get("min_score", Config.mutation_min),
        layers=tuple(data.get("layers", {}).get("order", ())),
    )
