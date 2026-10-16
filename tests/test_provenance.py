import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from gauntlet.provenance import MANIFEST, fingerprint, stamp, verify


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
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    git(tmp_path, "add", "a.py")
    git(tmp_path, "commit", "-q", "-m", "init", "--no-gpg-sign")
    return tmp_path


def test_fingerprint_is_stable(repo: Path) -> None:
    assert fingerprint(repo) == fingerprint(repo)


def test_fingerprint_changes_with_edits_new_files_and_commits(repo: Path) -> None:
    seen = {fingerprint(repo)}
    (repo / "a.py").write_text("x = 2\n")
    seen.add(fingerprint(repo))
    (repo / "b.py").write_text("y = 1\n")
    seen.add(fingerprint(repo))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "two", "--no-gpg-sign")
    seen.add(fingerprint(repo))
    assert len(seen) == 4


def test_fingerprint_ignores_excluded_paths(repo: Path) -> None:
    before = fingerprint(repo, exclude=("art",))
    (repo / "art").mkdir()
    (repo / "art" / "gocyclo.txt").write_text("1 p f a.go:1:1\n")
    assert fingerprint(repo, exclude=("art",)) == before
    assert fingerprint(repo) != before


def test_fingerprint_needs_a_git_repository(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a git repository"):
        fingerprint(tmp_path)


def test_repo_config_cannot_run_commands_through_our_git_calls(repo: Path, tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    git(repo, "config", "diff.external", str(script))
    git(repo, "config", "core.fsmonitor", str(script))
    (repo / "a.py").write_text("x = 3\n")
    fingerprint(repo)
    assert not marker.exists()


def make_artifacts(repo: Path) -> Path:
    art = repo / "art"
    art.mkdir()
    (art / "gocyclo.txt").write_text("1 p f a.go:1:1\n")
    return art


def test_stamp_then_verify(repo: Path) -> None:
    art = make_artifacts(repo)
    manifest = stamp(art, repo, ["gocyclo.txt"])
    assert (art / MANIFEST).exists()
    assert set(manifest) >= {"fingerprint", "files", "created"}
    assert verify(art, repo, ["gocyclo.txt"])["fingerprint"] == manifest["fingerprint"]


def test_verify_requires_a_manifest(repo: Path) -> None:
    art = make_artifacts(repo)
    with pytest.raises(ValueError, match="not stamped"):
        verify(art, repo, ["gocyclo.txt"])


def test_verify_detects_a_modified_artifact(repo: Path) -> None:
    art = make_artifacts(repo)
    stamp(art, repo, ["gocyclo.txt"])
    (art / "gocyclo.txt").write_text("1 p f a.go:1:1\n2 p g a.go:9:1\n")
    with pytest.raises(ValueError, match=r"gocyclo\.txt changed since it was stamped"):
        verify(art, repo, ["gocyclo.txt"])


def test_verify_detects_changed_source(repo: Path) -> None:
    art = make_artifacts(repo)
    stamp(art, repo, ["gocyclo.txt"])
    (repo / "a.py").write_text("x = 99\n")
    with pytest.raises(ValueError, match="stale"):
        verify(art, repo, ["gocyclo.txt"])


def test_verify_rejects_artifacts_the_manifest_does_not_cover(repo: Path) -> None:
    art = make_artifacts(repo)
    stamp(art, repo, ["gocyclo.txt"])
    (art / "cover-func.txt").write_text("late addition\n")
    with pytest.raises(ValueError, match=r"cover-func\.txt is not covered by the manifest"):
        verify(art, repo, ["gocyclo.txt", "cover-func.txt"])


def test_stamp_refuses_missing_artifacts(repo: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nothing.txt"):
        stamp(make_artifacts(repo), repo, ["nothing.txt"])


def test_manifest_is_plain_json(repo: Path) -> None:
    art = make_artifacts(repo)
    stamp(art, repo, ["gocyclo.txt"])
    data = json.loads((art / MANIFEST).read_text())
    assert list(data["files"]) == ["gocyclo.txt"]
    assert len(data["files"]["gocyclo.txt"]) == 64


def test_artifacts_outside_the_source_tree_work_too(repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    art = tmp_path_factory.mktemp("art")
    (art / "gocyclo.txt").write_text("1 p f a.go:1:1\n")
    stamp(art, repo, ["gocyclo.txt"])
    verify(art, repo, ["gocyclo.txt"])


def test_artifacts_at_the_source_root_are_not_excluded_wholesale(repo: Path) -> None:
    (repo / "coverage.json").write_text("{}")
    stamp(repo, repo, ["coverage.json"])
    verify(repo, repo, ["coverage.json"])  # positive control: unchanged source verifies
    (repo / "a.py").write_text("x = 5\n")
    with pytest.raises(ValueError, match="stale"):
        verify(repo, repo, ["coverage.json"])


def test_fingerprint_sees_binary_changes(repo: Path) -> None:
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02")
    git(repo, "add", "blob.bin")
    git(repo, "commit", "-q", "-m", "bin", "--no-gpg-sign")
    (repo / "blob.bin").write_bytes(b"\x00\x01\x03")
    first = fingerprint(repo)
    (repo / "blob.bin").write_bytes(b"\x00\x01\x04")
    assert fingerprint(repo) != first


def test_excluded_tracked_changes_are_ignored_but_others_count(repo: Path) -> None:
    (repo / "art").mkdir()
    (repo / "art" / "x.txt").write_text("1")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "art", "--no-gpg-sign")
    base = fingerprint(repo, exclude=("art",))
    (repo / "art" / "x.txt").write_text("2")
    assert fingerprint(repo, exclude=("art",)) == base
    (repo / "a.py").write_text("x = 7\n")
    assert fingerprint(repo, exclude=("art",)) != base


def test_textconv_drivers_never_run(repo: Path, tmp_path: Path) -> None:
    marker = tmp_path / "textconv-ran"
    script = tmp_path / "conv.sh"
    script.write_text(f'#!/bin/sh\ntouch {marker}\ncat "$1"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    (repo / ".gitattributes").write_text("*.py diff=evil\n")
    git(repo, "config", "diff.evil.textconv", str(script))
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-q", "-m", "attrs", "--no-gpg-sign")
    (repo / "a.py").write_text("x = 8\n")
    fingerprint(repo)
    assert not marker.exists()


def test_our_environment_does_not_leak_into_git(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = tmp_path / "env-ran"
    script = tmp_path / "ext.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(script))
    (repo / "a.py").write_text("x = 9\n")
    fingerprint(repo)
    assert not marker.exists()


def test_a_non_repository_is_reported_with_its_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=f"^{tmp_path} is not a git repository"):
        fingerprint(tmp_path)


def test_stamp_records_a_timestamp_and_the_exact_fingerprint(repo: Path) -> None:
    art = make_artifacts(repo)
    manifest = stamp(art, repo, ["gocyclo.txt"])
    assert manifest["fingerprint"] == fingerprint(repo, exclude=("art",))
    assert manifest["created"].endswith("+00:00")


def test_staged_but_uncommitted_changes_count(repo: Path) -> None:
    before = fingerprint(repo)
    (repo / "a.py").write_text("x = 42\n")
    git(repo, "add", "a.py")
    assert fingerprint(repo) != before


def test_gitignored_files_do_not_count(repo: Path) -> None:
    (repo / ".gitignore").write_text("junk.log\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore", "--no-gpg-sign")
    before = fingerprint(repo)
    (repo / "junk.log").write_text("noise\n")
    assert fingerprint(repo) == before


def test_untracked_content_counts_not_just_names(repo: Path) -> None:
    (repo / "new.py").write_text("a\n")
    first = fingerprint(repo)
    (repo / "new.py").write_text("b\n")
    assert fingerprint(repo) != first
