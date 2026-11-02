"""The language registry: every plugin is an entry point in the `gauntlet.languages` group."""

from functools import cache
from importlib.metadata import entry_points
from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.plugin import Language

GROUP = "gauntlet.languages"


@cache
def registry() -> dict[str, Language]:
    found: dict[str, Language] = {}
    for point in entry_points(group=GROUP):
        if point.name in found:
            raise GauntletError(f"two plugins register the language {point.name!r}; uninstall one")
        found[point.name] = point.load()
    return found


def names() -> str:
    return ", ".join(registry()) or "none installed"


def get(name: str) -> Language:
    if name not in registry():
        raise GauntletError(f"unsupported language {name!r}, expected one of {names()}")
    return registry()[name]


def detect(root: Path) -> list[str]:
    """The languages whose marker files exist in `root`, in registry order."""
    return [name for name, row in registry().items() if any(next(root.glob(m), None) for m in row.markers)]
