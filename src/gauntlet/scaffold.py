"""`gauntlet init`: a starter gauntlet.toml for an existing project. Never overwrites."""

from pathlib import Path

from gauntlet import languages
from gauntlet.errors import GauntletError

PYTHON = """language = "python"
src = "{src}"

# Optional: imports may only point down this list (outermost layer first), each a dotted module prefix.
# [layers]
# order = ["app.web", "app.service", "app.domain"]
"""


def _template(root: Path) -> str:
    if not languages.detect(root):
        markers = ", ".join(m for row in languages.TABLE.values() for m in row.markers)
        raise GauntletError(f"cannot tell the language of {root}: looked for {markers}")
    return PYTHON.format(src="src" if (root / "src").is_dir() else ".")


def write_config(root: Path) -> Path:
    path = root / "gauntlet.toml"
    if path.exists():
        raise GauntletError(f"{path.name} already exists; edit it instead")
    path.write_text(_template(root))
    return path
