"""`gauntlet init`: a starter gauntlet.toml for an existing project. Never overwrites."""

from pathlib import Path

from gauntlet import languages
from gauntlet.errors import GauntletError


def _template(root: Path) -> str:
    if not languages.registry():
        raise GauntletError('no language plugin is installed; install one, such as "gauntlet-core[python]"')
    found = languages.detect(root)
    if not found:
        markers = ", ".join(m for row in languages.registry().values() for m in row.markers)
        raise GauntletError(f"cannot tell the language of {root}: looked for {markers}")
    return languages.get(found[0]).template(root)


def write_config(root: Path) -> Path:
    path = root / "gauntlet.toml"
    if path.exists():
        raise GauntletError(f"{path.name} already exists; edit it instead")
    path.write_text(_template(root))
    return path
