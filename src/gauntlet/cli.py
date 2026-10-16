import argparse
import sys
from pathlib import Path

from gauntlet import arch, clean
from gauntlet.config import Config, load


def _arch(root: Path, cfg: Config) -> int:
    violations = arch.check(root / cfg.src, cfg.layers)
    for v in violations:
        print(f"{v.path}:{v.line}: {v.source} imports outer layer {v.target}")
    return 1 if violations else 0


def _clean(root: Path, cfg: Config) -> int:
    offenders = clean.check(root, root / "coverage.json", cfg.crap_max)
    for path, f in offenders:
        print(
            f"{path}:{f.line}: {f.name} CRAP {f.crap:.1f} > {cfg.crap_max} "
            f"(complexity {f.complexity}, coverage {f.coverage:.0%})"
        )
    return 1 if offenders else 0


GATES = {"arch": [_arch], "clean": [_clean], "check": [_arch, _clean]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gauntlet")
    parser.add_argument("gate", choices=GATES)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        cfg = load(args.root / "gauntlet.toml")
        if cfg.language != "python":
            raise ValueError(f"language {cfg.language!r} is not implemented yet")
        return max(gate(args.root, cfg) for gate in GATES[args.gate])
    except (FileNotFoundError, ValueError) as e:
        print(f"gauntlet: {e}", file=sys.stderr)
        return 2
