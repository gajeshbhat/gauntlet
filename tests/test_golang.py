import json
from pathlib import Path

import pytest

from gauntlet import golang
from gauntlet.safefs import read_artifact
from gauntlet.scope import parse

IMPORTS = """\
example.com/m/web fmt example.com/m/service example.com/m/domain
example.com/m/service example.com/m/domain
example.com/m/domain fmt example.com/m/web
example.com/m/other net/http
"""
LAYERS = ("example.com/m/web", "example.com/m/service", "example.com/m/domain")


def names(offenders: list[tuple[str, object]]) -> list[str]:
    return [getattr(f, "name") for _, f in offenders]  # noqa: B009


def test_arch_flags_outward_imports_only() -> None:
    (v,) = golang.arch_check(IMPORTS, LAYERS).violations
    assert (v.path, v.source, v.target) == ("example.com/m/domain", LAYERS[2], LAYERS[0])


def test_arch_without_layers_checks_nothing() -> None:
    assert golang.arch_check(IMPORTS, ()).violations == []


def mutation(*muts: tuple[str, str, int]) -> str:
    files: dict[str, list[dict[str, object]]] = {}
    for name, status, line in muts:
        files.setdefault(name, []).append({"type": "ARITHMETIC_BASE", "status": status, "line": line, "column": 3})
    return json.dumps({"files": [{"file_name": n, "mutations": m} for n, m in files.items()]})


def test_harden_counts_not_covered_as_failures() -> None:
    text = mutation(
        ("a.go", "KILLED", 1),
        ("a.go", "KILLED", 2),
        ("a.go", "LIVED", 3),
        ("a.go", "NOT COVERED", 4),
        ("a.go", "NOT COVERED", 5),
    )
    pct, bad, *_ = golang.harden_check(text, parse([]))
    assert pct == 40.0
    assert bad == [
        "a.go:3:3 ARITHMETIC_BASE LIVED",
        "a.go:4:3 ARITHMETIC_BASE NOT COVERED",
        "a.go:5:3 ARITHMETIC_BASE NOT COVERED",
    ]


def test_harden_timeouts_count_as_killed_and_unviable_are_ignored() -> None:
    text = mutation(("a.go", "TIMED OUT", 1), ("a.go", "NOT VIABLE", 2), ("a.go", "SKIPPED", 3))
    assert golang.harden_check(text, parse([])) == (100.0, [], 1, 1)


def test_harden_scope_filters_by_file_and_line() -> None:
    text = mutation(("a.go", "LIVED", 5), ("a.go", "KILLED", 50), ("b.go", "LIVED", 1))
    pct, bad, *_ = golang.harden_check(text, parse(["a.go:40-60"]))
    assert (pct, bad) == (100.0, [])


def test_harden_without_mutants_in_scope_is_an_error() -> None:
    with pytest.raises(ValueError, match="no mutants"):
        golang.harden_check(mutation(("a.go", "KILLED", 1)), parse(["zzz.go"]))


def test_load_artifacts_names_the_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="gocyclo.txt"):
        read_artifact(tmp_path, "gocyclo.txt", "gocyclo -over 0 ./...")


def test_arch_same_layer_imports_are_fine() -> None:
    assert golang.arch_check("example.com/m/domain example.com/m/domain/sub\n", LAYERS).violations == []


def test_arch_violation_has_no_line() -> None:
    (v,) = golang.arch_check(IMPORTS, LAYERS).violations
    assert v.line == 0


def test_harden_no_mutants_message() -> None:
    with pytest.raises(ValueError, match=r"^no mutants in scope; check the scope and that gremlins ran$"):
        golang.harden_check(mutation(("a.go", "KILLED", 1)), parse(["zzz.go"]))


def test_harden_paths_are_relative_to_the_mutation_dir() -> None:
    text = mutation(("disk.go", "LIVED", 5))
    pct, bad, *_ = golang.harden_check(text, parse(["lxd/device/disk.go:1-9"]), base="lxd/device")
    assert pct == 0.0
    assert bad == ["lxd/device/disk.go:5:3 ARITHMETIC_BASE LIVED"]


def test_harden_without_base_keeps_paths_as_reported() -> None:
    _, bad, *_ = golang.harden_check(mutation(("disk.go", "LIVED", 5)), parse([]))
    assert bad == ["disk.go:5:3 ARITHMETIC_BASE LIVED"]


def test_arch_counts_packages_in_layers() -> None:
    assert golang.arch_check(IMPORTS, LAYERS).modules == 3


def test_arch_collects_layer_edges() -> None:
    assert golang.arch_check(IMPORTS, LAYERS).edges == frozenset({(0, 1), (0, 2), (1, 2), (2, 0)})
