"""Builders for the Python plugin tests."""

import subprocess
from collections.abc import Mapping
from pathlib import Path


def tree(root: Path, files: Mapping[str, str]) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)  # the gates list sources through it
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
