"""`gauntlet init`: a starter gauntlet.toml for an existing project. Never overwrites."""

from pathlib import Path

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
PYTHON_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")


def _template(root: Path) -> str:
    python = any((root / m).exists() for m in PYTHON_MARKERS)
    go = (root / "go.mod").exists()
    if python and go:
        raise ValueError("both pyproject.toml and go.mod found; write gauntlet.toml yourself")
    if go:
        return GO
    if python:
        return PYTHON.format(src="src" if (root / "src").is_dir() else ".")
    raise ValueError(f"cannot tell the language of {root}: no pyproject.toml, requirements.txt or go.mod")


def write_config(root: Path) -> Path:
    path = root / "gauntlet.toml"
    if path.exists():
        raise ValueError(f"{path.name} already exists; edit it instead")
    text = _template(root)
    path.write_text(text)
    return path
