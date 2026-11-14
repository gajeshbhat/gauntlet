from pathlib import Path

import pytest
from helpers import git

from gauntlet.changed import entries, spans

OLD = "a\nb\nc\nd\ne\n"


@pytest.mark.parametrize(
    ("new", "expected"),
    [
        (OLD, []),
        ("a\nb\r\nc\nd\ne", []),  # line endings are not a change
        ("a\nB\nc\nd\ne\n", [(2, 2)]),
        ("a\nB\nC\nd\ne\n", [(2, 3)]),
        ("a\nb\nx\ny\nc\nd\ne\n", [(3, 4)]),
        ("x\na\nb\nc\nd\ne\nz\n", [(1, 1), (7, 7)]),
        ("a\nb\nd\ne\n", [(3, 3)]),  # c is gone: the line that took its place
        ("a\nb\nc\nd\n", [(4, 4)]),  # the last line is gone: the new last line
        ("b\nc\nd\ne\n", [(1, 1)]),
        ("", [(1, 1)]),
    ],
)
def test_spans_are_the_lines_of_the_new_text_that_differ(new: str, expected: list[tuple[int, int]]) -> None:
    assert spans(OLD, new) == expected


def test_an_added_file_text_is_one_span() -> None:
    assert spans("", "a\nb\n") == [(1, 2)]


def test_a_removed_last_line_points_at_the_one_line_left() -> None:
    assert spans("a\nb\n", "a\n") == [(1, 1)]


def test_every_file_is_compared_with_its_own_old_content(repo: Path) -> None:
    (repo / "empty.py").write_text("")
    (repo / "c.py").write_text("1\n2\n3\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "more", "--no-gpg-sign")
    (repo / "c.py").write_text("1\n2\n3\n4\n")
    (repo / "pkg" / "a.py").write_text("a\nb\nc\nd\nE\n")
    assert entries(repo, "HEAD", (".py",)) == [("c.py", (4, 4)), ("pkg/a.py", (5, 5))]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(OLD)
    (tmp_path / "b.py").write_text("one\ntwo\n")
    (tmp_path / "has space.py").write_text("x\n")
    (tmp_path / "notes.txt").write_text("old\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init", "--no-gpg-sign")
    return tmp_path


def test_nothing_changed_means_no_entries(repo: Path) -> None:
    assert entries(repo, "HEAD", (".py",)) == []


def test_entries_are_the_changed_ranges_of_source_files_only(repo: Path) -> None:
    (repo / "pkg" / "a.py").write_text("a\nB\nc\nd\ne\nf\n")
    (repo / "has space.py").write_text("x\ny\n")
    (repo / "notes.txt").write_text("new\n")  # not source
    (repo / "new.py").write_text("fresh\n")  # untracked: all of it
    (repo / "b.py").unlink()  # deleted: nothing left to check
    assert entries(repo, "HEAD", (".py",)) == [
        ("has space.py", (2, 2)),
        ("new.py", None),
        ("pkg/a.py", (2, 2)),
        ("pkg/a.py", (6, 6)),
    ]


def test_the_comparison_is_against_the_named_commit_and_includes_committed_work(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "b.py").write_text("one\nTWO\n")
    git(repo, "commit", "-q", "-am", "work", "--no-gpg-sign")
    (repo / "b.py").write_text("one\nTWO\nthree\n")
    assert entries(repo, "HEAD", (".py",)) == [("b.py", (3, 3))]
    assert entries(repo, "main", (".py",)) == [("b.py", (2, 3))]
    assert entries(repo, "HEAD~1", (".py",)) == [("b.py", (2, 3))]


def test_old_content_that_is_not_text_makes_the_whole_file_changed(repo: Path) -> None:
    (repo / "bin.py").write_bytes(b"\xff\xfe\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "bin", "--no-gpg-sign")
    (repo / "bin.py").write_text("text\n")
    assert entries(repo, "HEAD", (".py",)) == [("bin.py", (1, 1))]


def test_a_file_whose_name_holds_a_newline_is_in_scope_as_a_whole(repo: Path) -> None:
    (repo / "odd\nname.py").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "odd", "--no-gpg-sign")
    (repo / "b.py").write_text("one\n2\n")
    assert entries(repo, "HEAD", (".py",)) == [("b.py", (2, 2)), ("odd\nname.py", None)]


@pytest.mark.parametrize("ref", ["-x", "--output=/tmp/x", "a b", "", "a;b", "$(x)", "a\nb"])
def test_a_ref_that_could_be_an_option_or_more_is_refused(repo: Path, ref: str) -> None:
    with pytest.raises(ValueError, match=r"^bad --changed value .*: expected a commit, branch or tag$"):
        entries(repo, ref, (".py",))


@pytest.mark.parametrize("ref", ["HEAD", "main", "HEAD~0", "HEAD^{commit}", "main@{0}", "v1.0-rc_1/x"])
def test_ordinary_refs_are_allowed(repo: Path, ref: str) -> None:
    git(repo, "tag", "v1.0-rc_1/x")
    assert entries(repo, ref, (".py",)) == []


def test_a_ref_that_is_no_commit_is_a_clear_error(repo: Path) -> None:
    with pytest.raises(ValueError, match=rf"^--changed: 'nope' is not a commit in {repo}$"):
        entries(repo, "nope", (".py",))
    git(repo, "tag", "a-file", "HEAD:b.py")
    with pytest.raises(ValueError, match="'a-file' is not a commit"):
        entries(repo, "a-file", (".py",))
