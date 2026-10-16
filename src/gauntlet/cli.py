import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from gauntlet import arch, clean, golang, harden
from gauntlet.clean import Finding
from gauntlet.config import Config, load
from gauntlet.scope import Scope, parse

IMPORTS_HOW = "go list -e -f '{{.ImportPath}} {{join .Imports \" \"}}' ./..."


def _arch(root: Path, cfg: Config, scope: Scope) -> int:
    if cfg.language == "go":
        violations = golang.arch_check(golang.read(root, "imports.txt", IMPORTS_HOW), cfg.layers)
    else:
        violations = arch.check(root / cfg.src, cfg.layers)
    for v in violations:
        where = f"{v.path}:{v.line}" if v.line else v.path
        print(f"{where}: {v.source} imports outer layer {v.target}")
    return 1 if violations else 0


def _offenders(root: Path, cfg: Config, scope: Scope) -> list[tuple[str, Finding]]:
    if cfg.language == "go":
        return golang.clean_check(
            golang.read(root, "gocyclo.txt", "gocyclo ./..."),
            golang.read(
                root,
                "cover-func.txt",
                "go test -coverprofile=c.out ./... && go tool cover -func=c.out",
            ),
            cfg.crap_max,
            scope,
        )
    found = clean.check(root, root / "coverage.json", cfg.crap_max)
    return [(path, f) for path, f in found if scope.contains(path, f.line)]


def _clean(root: Path, cfg: Config, scope: Scope) -> int:
    offenders = _offenders(root, cfg, scope)
    for path, f in offenders:
        print(
            f"{path}:{f.line}: {f.name} CRAP {f.crap:.1f} > {cfg.crap_max} "
            f"(complexity {f.complexity}, coverage {f.coverage:.0%})"
        )
    return 1 if offenders else 0


def _harden(root: Path, cfg: Config, scope: Scope) -> int:
    if cfg.language == "go":
        pct, survivors = golang.harden_check(
            golang.read(root, "mutation.json", "gremlins unleash -o mutation.json ."), scope
        )
    else:
        pct, survivors = harden.check(root)
    for line in survivors:
        print(line)
    ok = pct >= cfg.mutation_min
    print(f"mutation score {pct:.1f}% {'>=' if ok else '<'} {cfg.mutation_min}%")
    return 0 if ok else 1


Gate = Callable[[Path, Config, Scope], int]
GATES: dict[str, list[Gate]] = {
    "arch": [_arch],
    "clean": [_clean],
    "harden": [_harden],
    "check": [_arch, _clean],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gauntlet")
    parser.add_argument("gate", choices=GATES)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="PATH[:LO-HI]",
        help="limit clean/harden to a file or line range (repeatable)",
    )
    args = parser.parse_args(argv)
    try:
        cfg = load(args.root / "gauntlet.toml")
        scope = parse(args.only)
        return max(gate(args.root, cfg, scope) for gate in GATES[args.gate])
    except (FileNotFoundError, ValueError) as e:
        print(f"gauntlet: {e}", file=sys.stderr)
        return 2
