import os
import subprocess
from pathlib import Path

import pytest

from gauntlet.snapshot import snapshot


def git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "pkg" / "a.py").write_text("a = 1\n")
    (root / "gone.py").write_text("gone\n")
    (root / ".gitignore").write_text("ignored.txt\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init", "--no-gpg-sign")
    return root


def test_copies_the_working_tree_state(repo: Path, tmp_path: Path) -> None:
    (repo / "pkg" / "a.py").write_text("a = 2\n")  # modified, uncommitted
    (repo / "new.py").write_text("new\n")  # untracked
    (repo / "ignored.txt").write_text("ignored\n")  # git-ignored
    (repo / "gone.py").unlink()  # deleted
    dest = tmp_path / "snap"
    snapshot(repo, dest)
    assert (dest / "pkg" / "a.py").read_text() == "a = 2\n"
    assert (dest / "new.py").read_text() == "new\n"
    assert not (dest / "ignored.txt").exists()
    assert not (dest / "gone.py").exists()
    assert not (dest / ".git").exists()
    copied = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert copied == [".gitignore", "new.py", "pkg/a.py"]


def test_the_destination_is_private(repo: Path, tmp_path: Path) -> None:
    dest = tmp_path / "snap"
    snapshot(repo, dest)
    assert dest.stat().st_mode & 0o777 == 0o700


def test_refuses_a_non_empty_destination(repo: Path, tmp_path: Path) -> None:
    dest = tmp_path / "snap"
    dest.mkdir()
    (dest / "x").write_text("x")
    with pytest.raises(ValueError, match="not empty"):
        snapshot(repo, dest)


def test_symlinks_inside_the_repo_are_copied_as_files(repo: Path, tmp_path: Path) -> None:
    (repo / "link.py").symlink_to(repo / "pkg" / "a.py")
    dest = tmp_path / "snap"
    snapshot(repo, dest)
    assert not (dest / "link.py").is_symlink()
    assert (dest / "link.py").read_text() == "a = 1\n"


def test_symlinks_leaving_the_repo_are_refused(repo: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("secret\n")
    (repo / "link.txt").symlink_to(secret)
    with pytest.raises(ValueError, match="escapes the project root"):
        snapshot(repo, tmp_path / "snap")


def test_enforces_a_size_cap(repo: Path, tmp_path: Path) -> None:
    (repo / "big.bin").write_bytes(b"x" * 100)
    with pytest.raises(ValueError, match="over the 50 byte limit"):
        snapshot(repo, tmp_path / "snap", max_bytes=50)


def test_enforces_a_file_count_cap(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="more than 2 files"):
        snapshot(repo, tmp_path / "snap", max_files=2)


def test_needs_a_git_repository(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    with pytest.raises(ValueError, match="not a git repository"):
        snapshot(tmp_path / "plain", tmp_path / "snap")


def test_file_modes_are_kept(repo: Path, tmp_path: Path) -> None:
    script = repo / "run.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    snapshot(repo, tmp_path / "snap")
    assert (tmp_path / "snap" / "run.sh").stat().st_mode & 0o111
