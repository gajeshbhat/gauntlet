"""Real mutmut runs on a throwaway project; slow (needs uv and its cache)."""

import textwrap
from pathlib import Path

import pytest

from gauntlet.cli import main

PYPROJECT = """
[project]
name = "victim"
version = "0"
requires-python = ">=3.12"
dependencies = []
[dependency-groups]
dev = ["pytest", "mutmut"]
[tool.mutmut]
source_paths = ["src/victim/"]
pytest_add_cli_args = ["-p", "no:cacheprovider"]
[tool.pytest.ini_options]
pythonpath = ["src"]
"""
CODE = "def add(a: int, b: int) -> int:\n    return a + b\n"
WEAK = "from victim import add\n\ndef test_runs():\n    add(1, 2)\n"
STRONG = WEAK.replace("    add(1, 2)\n", "    assert add(1, 2) == 3\n    assert add(2, 2) == 4\n")


def victim(root: Path, test: str) -> Path:
    (root / "src" / "victim").mkdir(parents=True)
    (root / "src" / "victim" / "__init__.py").write_text(CODE)
    (root / "tests").mkdir()
    (root / "tests" / "test_add.py").write_text(test)
    (root / "pyproject.toml").write_text(textwrap.dedent(PYPROJECT))
    (root / "gauntlet.toml").write_text('language = "python"\n[mutation]\nmin_score = 90\n')
    return root


@pytest.mark.parametrize(("test", "code"), [(WEAK, 1), (STRONG, 0)])
def test_harden_against_real_mutmut(
    tmp_path: Path, test: str, code: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["harden", str(victim(tmp_path, test))]) == code
    assert "mutation score" in capsys.readouterr().out
