import pytest
from fakelang import FAKE

from gauntlet import linecov


@pytest.mark.parametrize("text", ["garbage: [[[", '{"files": {"a.py": {}}}'])
def test_malformed_reports_are_clean_errors(text: str) -> None:
    with pytest.raises(ValueError, match="^cannot read fakecov report$"):
        linecov.parse(FAKE, text)


def test_a_report_is_read_by_the_plugin() -> None:
    report = '{"files": {"a.py": {"executed_lines": [1], "missing_lines": [2]}}}'
    assert linecov.parse(FAKE, report) == {"a.py": {1: 1, 2: 0}}


@pytest.mark.parametrize(
    ("key", "files", "expected"),
    [
        ("src/a.py", ["src/a.py", "src/b.py"], "src/a.py"),
        ("pkg/a.py", ["src/pkg/a.py"], "src/pkg/a.py"),
        ("/project/src/b.py", ["src/b.py"], "src/b.py"),
        ("/home/me/proj/src/b.py", ["src/b.py"], "src/b.py"),
    ],
)
def test_coverage_paths_match_source_files_by_path_suffix(key: str, files: list[str], expected: str) -> None:
    assert linecov.locate(key, files) == expected


def test_a_name_that_only_ends_the_same_is_not_a_match() -> None:
    assert linecov.locate("a.py", ["pkg/data.py", "pkg/beta.py"]) is None


def test_ambiguous_suffix_is_an_error() -> None:
    with pytest.raises(ValueError, match="matches more than one file"):
        linecov.locate("a.py", ["x/a.py", "y/a.py"])


@pytest.mark.parametrize("key", ["../secret.py", "a/../../secret.py", "/project/../etc/passwd"])
def test_paths_that_climb_out_are_refused(key: str) -> None:
    with pytest.raises(ValueError, match="escapes the project root"):
        linecov.locate(key, ["secret.py"])


def test_extra_leading_directories_are_only_accepted_where_a_report_legitimately_has_them() -> None:
    assert linecov.locate("extra/index.py", ["index.py"]) is None  # a relative path with a prefix: not ours
    assert linecov.locate("/home/me/proj/index.py", ["index.py"]) == "index.py"  # a host path outside the container
    assert linecov.locate("/home/me/proj/.venv/foo/index.py", ["index.py"]) is None  # a dependency
