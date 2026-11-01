"""Which modules a Python source imports, for the arch gate."""

import ast

from gauntlet.errors import GauntletError


def _resolve(node: ast.ImportFrom, package: list[str]) -> str:
    if node.level == 0:
        return node.module or ""  # pragma: no mutate (module is only None for relative imports)
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _walk(source: str, package: list[str]) -> list[tuple[int, str]]:
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


def imports_at(source: str, package: list[str]) -> list[tuple[int, str]]:
    try:
        return _walk(source, package)
    except (SyntaxError, RecursionError, MemoryError) as e:
        raise GauntletError(type(e).__name__) from None


def imports(source: str, package: str) -> set[str]:
    """Names imported by `source` living in dotted `package` (where relative imports resolve)."""
    return {name for _, name in imports_at(source, package.split(".") if package else [])}
