"""Arch gate: modules may import their own layer or inner layers, never outer ones.

`layers` is outermost first (e.g. web, service, domain). Each entry is a dotted module prefix.
ponytail: Python `ast` scan, no import-linter; add it if indirect-import analysis is needed.
"""

import ast
from dataclasses import dataclass
from pathlib import Path


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
    for i, prefix in enumerate(layers):
        if module == prefix or module.startswith(prefix + sep):
            return i
    return None


def check(root: Path, layers: tuple[str, ...]) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).with_suffix("").parts
        module = ".".join(parts)  # a package __init__ is "pkg.__init__", still inside layer "pkg"
        own = layer_of(module, layers)
        if own is None:
            continue
        seen: set[tuple[int, str]] = set()
        for line, name in _imports_at(path.read_text(), list(parts[:-1])):
            target = layer_of(name, layers)
            if target is not None and target < own and (line, layers[target]) not in seen:
                seen.add((line, layers[target]))
                violations.append(Violation(str(path.relative_to(root)), line, layers[own], layers[target]))
    return violations
