"""Go adapters. Gates consume artifacts produced by the target's own toolchain (run wherever it builds):

gocyclo.txt     gocyclo ./...
cover-func.txt  go test -coverprofile=c.out ./... && go tool cover -func=c.out
imports.txt     go list -e -f '{{.ImportPath}} {{join .Imports " "}}' ./...
mutation.json   gremlins unleash -o mutation.json .
"""

import json
import re
from pathlib import Path

from gauntlet.arch import ArchResult, Violation, layer_of
from gauntlet.clean import CleanResult, Finding
from gauntlet.crap import crap_score
from gauntlet.results import Mutation
from gauntlet.safefs import MAX_ARTIFACT_BYTES, read_text
from gauntlet.scope import Scope

COVER_LINE = re.compile(r"^(.+?):(\d+):\s+\S.*?\s+([\d.]+)%$")
CAUGHT = {"KILLED", "TIMED OUT"}
IGNORED = {"NOT VIABLE", "SKIPPED"}


def read(root: Path, name: str, how: str) -> str:
    path = root / name
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; produce it with: {how}")
    return read_text(path, MAX_ARTIFACT_BYTES)


def _gocyclo(text: str) -> list[tuple[str, int, str, int]]:
    rows: list[tuple[str, int, str, int]] = []
    for line in filter(None, (raw.strip() for raw in text.splitlines())):
        parts = line.split()
        try:
            path, row, _col = parts[-1].rsplit(":", 2)
            rows.append((path, int(row), " ".join(parts[2:-1]), int(parts[0])))
        except (ValueError, IndexError):
            raise ValueError(f"cannot parse gocyclo line {line!r}") from None
    return rows


def _coverage(text: str) -> dict[int, list[tuple[str, float]]]:
    by_line: dict[int, list[tuple[str, float]]] = {}
    for raw in text.splitlines():
        match = COVER_LINE.match(raw)
        if match:
            by_line.setdefault(int(match[2]), []).append((match[1], float(match[3]) / 100))
    return by_line


def _function_coverage(path: str, row: int, covered: dict[int, list[tuple[str, float]]]) -> float:
    for cover_path, fraction in covered.get(row, []):
        if cover_path == path or cover_path.endswith("/" + path):
            return fraction
    return 0.0  # absent from the profile: nothing exercised it (fail closed)


def clean_check(gocyclo: str, cover_func: str, crap_max: float, scope: Scope) -> CleanResult:
    covered = _coverage(cover_func)
    evaluated = 0
    offenders: list[tuple[str, Finding]] = []
    for path, row, name, complexity in _gocyclo(gocyclo):
        if not scope.contains(path, row):
            continue
        evaluated += 1
        fraction = _function_coverage(path, row, covered)
        crap = crap_score(complexity, fraction)
        if crap > crap_max:
            offenders.append((path, Finding(name, row, complexity, fraction, crap)))
    return CleanResult(evaluated, offenders)


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
