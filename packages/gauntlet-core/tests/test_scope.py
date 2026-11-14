import pytest

from gauntlet.scope import Scope, parse


def test_empty_scope_contains_everything() -> None:
    assert parse([]).contains("a/b.go", 5)


def test_path_entry_matches_whole_file_by_suffix() -> None:
    scope = parse(["lxd/device/disk.go"])
    assert scope.contains("lxd/device/disk.go", 1)
    assert scope.contains("github.com/x/lxd/device/disk.go", 99)


def test_path_entry_does_not_match_partial_names() -> None:
    scope = parse(["disk.go"])
    assert not scope.contains("lxd/device/mydisk.go", 1)
    assert scope.contains("lxd/device/disk.go", 1)


def test_range_entry_is_inclusive() -> None:
    scope = parse(["a.go:10-20"])
    assert [scope.contains("a.go", n) for n in (9, 10, 20, 21)] == [False, True, True, False]


def test_multiple_entries_are_a_union() -> None:
    scope = parse(["a.go:1-2", "b.go"])
    assert scope.contains("a.go", 2)
    assert scope.contains("b.go", 500)
    assert not scope.contains("c.go", 1)


@pytest.mark.parametrize("bad", ["a.go:x-2", "a.go:3", "a.go:5-2", ""])
def test_bad_entries_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="scope"):
        parse([bad])


def test_scope_is_a_value() -> None:
    assert parse(["a.go"]) == Scope((("a.go", None),))


def test_a_colon_inside_the_path_is_kept() -> None:
    assert parse(["dir:x/a.go:3-4"]) == Scope((("dir:x/a.go", (3, 4)),))


def test_directory_entries_match_everything_below_them() -> None:
    scope = parse(["src/"])
    assert scope.contains("src/gauntlet/cli.py", 3)
    assert scope.contains("pkg/src/x.py", 1)
    assert not scope.contains("tests/test_cli.py", 1)
    assert not scope.contains("mysrc/x.py", 1)


def test_directory_entries_take_no_line_range() -> None:
    with pytest.raises(ValueError, match="scope"):
        parse(["src/:1-5"])


def test_a_span_is_in_scope_when_any_of_its_lines_is() -> None:
    scope = parse(["a.go:10-20"])
    spans = [(1, 9), (1, 10), (15, 16), (20, 30), (21, 30), (1, 30)]
    assert [scope.overlaps("a.go", lo, hi) for lo, hi in spans] == [False, True, True, True, False, True]
    assert not scope.overlaps("b.go", 15, 16)
    assert parse(["a.go"]).overlaps("a.go", 1, 2)
    assert parse([]).overlaps("anything", 1, 2)


def test_files_are_the_names_an_entry_points_at() -> None:
    names = ["src/a.go", "src/b.go", "lib/c/d.go"]
    assert parse(["a.go:5-6", "lib/"]).files(names) == ["src/a.go", "lib/c/d.go"]
    assert parse([]).files(names) == []


def test_a_scope_reads_as_only_takes_it() -> None:
    assert str(parse(["a.go:10-20", "lib/", "b.go"])) == "a.go:10-20, lib/, b.go"
    assert str(parse([])) == "all source"
