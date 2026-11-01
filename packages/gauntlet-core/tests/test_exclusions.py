from pathlib import Path

import pytest
from helpers import tree

from gauntlet.exclusions import pragmas
from gauntlet.scope import Scope, parse


def test_counts_every_kind_of_exclusion_comment(tmp_path: Path) -> None:
    tree(tmp_path, {"a.py": "x = 1  # pragma: no mutate\ny = 2  # pragma: no cover\nz = 3  # nosec\nw = 4\n"})
    assert pragmas(tmp_path, "fake", Scope()) == [
        "a.py:1: x = 1  # pragma: no mutate",
        "a.py:2: y = 2  # pragma: no cover",
        "a.py:3: z = 3  # nosec",
    ]


def test_only_files_of_the_language_and_not_vendored_dirs(tmp_path: Path) -> None:
    tree(tmp_path, {".venv/lib/x.py": "# pragma: no cover\n"})
    tree(tmp_path, {"node_modules/m.py": "# pragma: no cover\n"})
    tree(tmp_path, {"notes.txt": "# pragma: no cover\n"})
    tree(tmp_path, {"src/real.py": "y = 1  # pragma: no cover\n"})
    assert pragmas(tmp_path, "fake", Scope()) == ["src/real.py:1: y = 1  # pragma: no cover"]


def test_scope_limits_the_files_and_lines_counted(tmp_path: Path) -> None:
    tree(tmp_path, {"a.py": "# nosec\n\n# nosec\n"})
    assert len(pragmas(tmp_path, "fake", parse(["a.py:3-3"]))) == 1
    assert pragmas(tmp_path, "fake", parse(["b.py"])) == []


def test_symlinks_out_of_the_root_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.py").write_text("# nosec\n")
    (root / "link.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(ValueError, match="escapes the project root"):
        pragmas(root, "fake", Scope())


def test_sources_the_plugin_cannot_read_are_errors(tmp_path: Path) -> None:
    tree(tmp_path, {"bad.py": "BROKEN\n"})
    with pytest.raises(ValueError, match=r"^cannot analyse bad\.py: BrokenSource$"):
        pragmas(tmp_path, "fake", Scope())
