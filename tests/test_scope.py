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
