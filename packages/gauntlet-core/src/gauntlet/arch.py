"""Arch gate: modules may import their own layer or inner layers, never outer ones.

`layers` is outermost first (e.g. web, service, domain). Each entry is a dotted module prefix.
Imports are read by the language plugin; direct imports only, no indirect-import analysis.
"""

from dataclasses import dataclass
from pathlib import Path

from gauntlet.config import Rule
from gauntlet.errors import GauntletError
from gauntlet.plugin import Language
from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    source: str
    target: str
    forbidden: bool = False  # a `forbid` rule, not the layer order


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


def _under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _forbidden(rel: Path, module: str, forbid: tuple[Rule, ...], found: list[tuple[int, str]]) -> list[Violation]:
    out: list[Violation] = []
    for rule in forbid:
        if not _under(module, rule.source):
            continue
        seen: set[int] = set()
        for line, name in found:
            if _under(name, rule.target) and not any(_under(name, a) for a in rule.allow) and line not in seen:
                seen.add(line)
                out.append(Violation(str(rel), line, module, rule.target, forbidden=True))
    return out


def _edges(own: int, layers: tuple[str, ...], found: list[tuple[int, str]]) -> set[tuple[int, int]]:
    targets = {layer_of(name, layers) for _, name in found}
    return {(own, t) for t in targets if t is not None and t != own}


def _imports_of(root: Path, rel: Path, language: Language, package: list[str], max_bytes: int) -> list[tuple[int, str]]:
    try:
        return language.imports(read_text(inside(root, str(rel)), max_bytes), package)
    except GauntletError as e:
        raise GauntletError(f"cannot analyse {rel}: {e}") from None


def check(
    root: Path,
    layers: tuple[str, ...],
    language: Language,
    max_bytes: int = MAX_SOURCE_BYTES,
    forbid: tuple[Rule, ...] = (),
) -> ArchResult:
    modules = 0
    violations: list[Violation] = []
    edges: set[tuple[int, int]] = set()
    for path in sorted(p for suffix in language.suffixes for p in root.rglob(f"*{suffix}")):
        rel = path.relative_to(root)
        parts = rel.with_suffix("").parts
        module = ".".join(parts)  # a package __init__ is "pkg.__init__", still inside layer "pkg"
        own = layer_of(module, layers)
        if own is not None:
            modules += 1
            found = _imports_of(root, rel, language, list(parts[:-1]), max_bytes)
            violations += _violations(rel, layers, own, found) + _forbidden(rel, module, forbid, found)
            edges |= _edges(own, layers, found)
    return ArchResult(modules, violations, frozenset(edges))


def _merge(results: list[ArchResult]) -> ArchResult:
    return ArchResult(
        sum(r.modules for r in results),
        [v for r in results for v in r.violations],
        frozenset(e for r in results for e in r.edges),
    )


def check_roots(
    base: Path, roots: tuple[str, ...], layers: tuple[str, ...], language: Language, forbid: tuple[Rule, ...] = ()
) -> ArchResult:
    """`check` every root under `base`; each must hold at least one layered module, or the gate saw nothing there."""
    results = [check(base / root, layers, language, forbid=forbid) for root in roots]
    for root, r in zip(roots, results, strict=True):
        if r.modules == 0:
            raise GauntletError(f"no module under {root} belongs to any configured layer; check [layers] and roots")
    return _merge(results)
