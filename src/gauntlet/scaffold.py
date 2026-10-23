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
GO = """language = "go"

# Optional, all under [go]:
[go]
# packages = ["./..."]            # package patterns the sandbox tests
# mutation_dir = "internal/pkg"   # where gremlins runs; its file names are relative to it
# mutate_only = ["handler.go"]    # mutate only these files (relative to mutation_dir)

# Optional: imports may only point down this list (outermost layer first), each a Go import path prefix.
# [layers]
# order = ["example.com/app/cmd", "example.com/app/internal/service", "example.com/app/internal/domain"]
"""
OTHER = """language = "{language}"
"""
TEMPLATES = {"python": PYTHON, "go": GO}


def _template(root: Path) -> str:
    found = languages.detect(root)
    if len(found) > 1:
        raise GauntletError(f"found {' and '.join(found)}; write gauntlet.toml yourself")
    if not found:
        markers = ", ".join(m for row in languages.TABLE.values() for m in row.markers)
        raise GauntletError(f"cannot tell the language of {root}: looked for {markers}")
    template = TEMPLATES.get(found[0], OTHER)
    return template.format(language=found[0], src="src" if (root / "src").is_dir() else ".")


def write_config(root: Path) -> Path:
    path = root / "gauntlet.toml"
    if path.exists():
        raise GauntletError(f"{path.name} already exists; edit it instead")
    path.write_text(_template(root))
    return path
