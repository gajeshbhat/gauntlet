"""Go adapters. Gates consume artifacts produced by the target's own toolchain (run wherever it builds):

cover.out       go test -coverprofile=cover.out ./...
imports.txt     go list -e -f '{{.ImportPath}} {{join .Imports " "}}' ./...
mutation.json   gremlins unleash -o mutation.json .
"""

import json
from pathlib import Path

from gauntlet.arch import ArchResult, Violation, layer_of
from gauntlet.results import Mutation
from gauntlet.safefs import MAX_ARTIFACT_BYTES, read_text
from gauntlet.scope import Scope

CAUGHT = {"KILLED", "TIMED OUT"}
IGNORED = {"NOT VIABLE", "SKIPPED"}


def read(root: Path, name: str, how: str) -> str:
    path = root / name
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; produce it with: {how}")
    return read_text(path, MAX_ARTIFACT_BYTES)


def _outward(package: str, imported: list[str], layers: tuple[str, ...]) -> list[Violation]:
    own = layer_of(package, layers, "/")
    if own is None:
        return []
    outer = {t for t in (layer_of(name, layers, "/") for name in imported) if t is not None and t < own}
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


def harden_check(mutation_json: str, scope: Scope, base: str = "") -> Mutation:
    caught, total = 0, 0
    bad: list[str] = []
    for file in json.loads(mutation_json)["files"]:
        name = f"{base}/{file['file_name']}" if base else file["file_name"]
        for m in file["mutations"]:
            if not scope.contains(name, m["line"]) or m["status"] in IGNORED:
                continue
            total += 1
            if m["status"] in CAUGHT:
                caught += 1
            else:
                bad.append(f"{name}:{m['line']}:{m['column']} {m['type']} {m['status']}")
    if total == 0:
        raise ValueError("no mutants in scope; check the scope and that gremlins ran")
    return Mutation(100 * caught / total, bad, caught, total)
