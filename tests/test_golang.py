from pathlib import Path

import pytest

from gauntlet import golang
from gauntlet.safefs import read_artifact

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


def test_load_artifacts_names_the_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="gocyclo.txt"):
        read_artifact(tmp_path, "gocyclo.txt", "gocyclo -over 0 ./...")


def test_arch_same_layer_imports_are_fine() -> None:
    assert golang.arch_check("example.com/m/domain example.com/m/domain/sub\n", LAYERS).violations == []


def test_arch_violation_has_no_line() -> None:
    (v,) = golang.arch_check(IMPORTS, LAYERS).violations
    assert v.line == 0


def test_arch_counts_packages_in_layers() -> None:
    assert golang.arch_check(IMPORTS, LAYERS).modules == 3


def test_arch_collects_layer_edges() -> None:
    assert golang.arch_check(IMPORTS, LAYERS).edges == frozenset({(0, 1), (0, 2), (1, 2), (2, 0)})
