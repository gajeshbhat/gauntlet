"""Go adapters. Gates consume artifacts produced by the target's own toolchain (run wherever it builds):

cover.out       go test -coverprofile=cover.out ./...
imports.txt     go list -e -f '{{.ImportPath}} {{join .Imports " "}}' ./...
mutation.json   gremlins unleash -o mutation.json .
"""

from gauntlet.arch import ArchResult, Violation, layer_of


def _outward(package: str, imported: list[str], layers: tuple[str, ...]) -> list[Violation]:
    own = layer_of(package, layers, "/")
    if own is None:
        return []
    outer = {t for t in _targets(imported, layers) if t < own}
    return [Violation(package, 0, layers[own], layers[t]) for t in sorted(outer)]


def _targets(imported: list[str], layers: tuple[str, ...]) -> set[int]:
    return {t for t in (layer_of(n, layers, "/") for n in imported) if t is not None}


def _edges(rows: list[list[str]], layers: tuple[str, ...]) -> frozenset[tuple[int, int]]:
    pairs = [(layer_of(r[0], layers, "/"), _targets(r[1:], layers)) for r in rows]
    return frozenset((own, t) for own, targets in pairs if own is not None for t in targets if t != own)


def arch_check(imports: str, layers: tuple[str, ...]) -> ArchResult:
    rows = [line.split() for line in imports.splitlines() if line.strip()]
    modules = sum(layer_of(r[0], layers, "/") is not None for r in rows)
    violations = [v for package, *imported in rows for v in _outward(package, imported, layers)]
    return ArchResult(modules, violations, _edges(rows, layers))
