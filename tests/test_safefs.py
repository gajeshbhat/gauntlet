from pathlib import Path

import pytest

from gauntlet.safefs import inside, read_text


def test_inside_accepts_nested_paths(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.py").write_text("x")
    assert inside(tmp_path, "a/b.py") == (tmp_path / "a" / "b.py").resolve()


@pytest.mark.parametrize("rel", ["../outside.py", "a/../../outside.py", "/etc/passwd"])
def test_inside_rejects_escapes(tmp_path: Path, rel: str) -> None:
    with pytest.raises(ValueError, match="escapes the project root"):
        inside(tmp_path, rel)


def test_inside_rejects_symlinks_that_leave_the_root(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside.py"
    root.mkdir()
    outside.write_text("x")
    (root / "link.py").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes the project root"):
        inside(root, "link.py")


def test_inside_allows_symlinks_that_stay_inside(tmp_path: Path) -> None:
    (tmp_path / "real.py").write_text("x")
    (tmp_path / "link.py").symlink_to(tmp_path / "real.py")
    assert inside(tmp_path, "link.py") == (tmp_path / "real.py").resolve()


def test_read_text_enforces_the_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    path.write_text("x" * 11)
    assert read_text(path, 11) == "x" * 11
    with pytest.raises(ValueError, match="over the 10 byte limit"):
        read_text(path, 10)


def test_read_text_rejects_undecodable_files(tmp_path: Path) -> None:
    path = tmp_path / "bin.py"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        read_text(path, 100)


def test_source_files_lists_by_suffix_and_skips_vendored_directories(tmp_path: Path) -> None:
    from gauntlet.safefs import source_files

    for rel in ("a.py", "pkg/b.py", "pkg/c.txt", ".venv/x.py", "node_modules/m/y.py", "pkg/sub/d.PY"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("")
    assert source_files(tmp_path, (".py",)) == ["a.py", "pkg/b.py"]
    assert source_files(tmp_path, (".py", ".txt")) == ["a.py", "pkg/b.py", "pkg/c.txt"]
