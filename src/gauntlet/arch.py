"""Arch gate: modules may import their own layer or inner layers, never outer ones.

`layers` is outermost first (e.g. web, service, domain). Each entry is a dotted module prefix.
ponytail: Python `ast` scan, no import-linter; add it if indirect-import analysis is needed.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    source: str
    target: str


def _resolve(node: ast.ImportFrom, package: list[str]) -> str:
    if node.level == 0:
        return node.module or ""  # pragma: no mutate (module is only None for relative imports)
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _imports_at(source: str, package: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node, package)
            found += [(node.lineno, f"{base}.{a.name}" if base else a.name) for a in node.names]
            if base:
                found.append((node.lineno, base))
    return found


def imports(source: str, package: str) -> set[str]:
    """Names imported by `source` living in dotted `package` (where relative imports resolve)."""
    return {name for _, name in _imports_at(source, package.split(".") if package else [])}


def layer_of(module: str, layers: tuple[str, ...], sep: str = ".") -> int | None:
    """Index of the layer with the longest prefix matching `module`, if any."""
    matches = [(len(p), i) for i, p in enumerate(layers) if module == p or module.startswith(p + sep)]
    return max(matches)[1] if matches else None


@dataclass(frozen=True)
class ArchResult:
    modules: int  # modules that belong to a layer; 0 means the gate saw nothing and must not pass
    violations: list[Violation]
    edges: frozenset[tuple[int, int]] = frozenset()  # (importer layer, imported layer) between different layers


def _violations(rel: Path, layers: tuple[str, ...], own: int, found: list[tuple[int, str]]) -> list[Violation]:
    out: list[Violation] = []
    seen: set[tuple[int, str]] = set()
    for line, name in found:
        target = layer_of(name, layers)
        if target is not None and target < own and (line, layers[target]) not in seen:
            seen.add((line, layers[target]))
            out.append(Violation(str(rel), line, layers[own], layers[target]))
    return out


def _edges(own: int, layers: tuple[str, ...], found: list[tuple[int, str]]) -> set[tuple[int, int]]:
    targets = {layer_of(name, layers) for _, name in found}
    return {(own, t) for t in targets if t is not None and t != own}


def _imports_of(root: Path, rel: Path, package: list[str], max_bytes: int) -> list[tuple[int, str]]:
    try:
        return _imports_at(read_text(inside(root, str(rel)), max_bytes), package)
    except (SyntaxError, RecursionError, MemoryError) as e:
        raise GauntletError(f"cannot analyse {rel}: {type(e).__name__}") from None


def check(root: Path, layers: tuple[str, ...], max_bytes: int = MAX_SOURCE_BYTES) -> ArchResult:
    modules = 0
    violations: list[Violation] = []
    edges: set[tuple[int, int]] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        parts = rel.with_suffix("").parts
        own = layer_of(".".join(parts), layers)  # a package __init__ is "pkg.__init__", still inside layer "pkg"
        if own is not None:
            modules += 1
            found = _imports_of(root, rel, list(parts[:-1]), max_bytes)
            violations += _violations(rel, layers, own, found)
            edges |= _edges(own, layers, found)
    return ArchResult(modules, violations, frozenset(edges))
