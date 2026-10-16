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


def _resolve(node: ast.ImportFrom, module: str, is_package: bool) -> str:
    if node.level == 0:
        return node.module or ""
    package = module.split(".")
    if not is_package:
        package = package[:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _imports_at(source: str, module: str, is_package: bool) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node, module, is_package)
            found.append((node.lineno, base))
            found += [(node.lineno, f"{base}.{a.name}") for a in node.names]
    return found


def imports(source: str, module: str, is_package: bool) -> set[str]:
    return {name for _, name in _imports_at(source, module, is_package)}


def _layer(module: str, layers: tuple[str, ...]) -> int | None:
    for i, prefix in enumerate(layers):
        if module == prefix or module.startswith(prefix + "."):
            return i
    return None


def check(root: Path, layers: tuple[str, ...]) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).with_suffix("").parts
        is_package = parts[-1] == "__init__"
        module = ".".join(parts[:-1] if is_package else parts)
        own = _layer(module, layers)
        if own is None:
            continue
        seen: set[tuple[int, str]] = set()
        for line, name in _imports_at(path.read_text(), module, is_package):
            target = _layer(name, layers)
            if target is not None and target < own and (line, layers[target]) not in seen:
                seen.add((line, layers[target]))
                violations.append(
                    Violation(str(path.relative_to(root)), line, layers[own], layers[target])
                )
    return violations
