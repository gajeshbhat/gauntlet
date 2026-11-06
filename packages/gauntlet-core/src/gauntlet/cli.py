import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from gauntlet import (
    arch,
    backends,
    clean,
    diagram,
    exclusions,
    languages,
    linecov,
    policy,
    provenance,
    report,
    runner,
    scaffold,
    spec,
)
from gauntlet.config import Config, load
from gauntlet.errors import GauntletError
from gauntlet.policy import SANDBOXES, Policy
from gauntlet.results import GateResult
from gauntlet.safefs import read_artifact
from gauntlet.sandbox import Sandbox
from gauntlet.scope import Scope, parse


@dataclass(frozen=True)
class Run:
    root: Path  # where gauntlet.toml and the target's sources live
    art: Path  # where artifacts (coverage.json, gocyclo.txt, ...) are read from
    source: Path  # the git checkout the artifacts must have been produced from
    cfg: Config  # effective config: the repo's values after the policy has been applied
    scope: Scope
    policy: Policy
    feature: Path | None = None  # the Gherkin file for the spec gate


def _trusted(run: Run, names: list[str]) -> None:
    """Refuse artifacts that were not produced from this exact source (unless the policy allows it)."""
    if not run.policy.allow_unstamped:
        provenance.verify(run.art, run.source, names)


def _arch_result(run: Run) -> arch.ArchResult:
    cfg = run.cfg
    if not cfg.layers:
        raise GauntletError("no layers configured: add [layers] order to gauntlet.toml")
    return arch.check_roots(run.root, cfg.roots or (cfg.src,), cfg.layers, languages.get(cfg.language), cfg.forbid)


def _arch(run: Run) -> GateResult:
    result = _arch_result(run)
    found = tuple(
        f"{v.path}:{v.line}: {v.source} imports {'forbidden' if v.forbidden else 'outer layer'} {v.target}"
        for v in result.violations
    )
    summary = f"arch: {result.modules} module(s) checked, {len(found)} violation(s)"
    return GateResult("arch", not found, summary, found, {"modules": result.modules, "violations": len(found)})


def _clean(run: Run) -> GateResult:
    language = languages.get(run.cfg.language)
    _trusted(run, [language.coverage_file])
    text = read_artifact(
        run.art, language.coverage_file, f"gauntlet run, or your test runner's {language.coverage_file} report"
    )
    lines = linecov.parse(language, text)
    result = clean.check(run.root, lines, language, run.cfg.crap_max, run.scope)
    if result.evaluated == 0:
        raise GauntletError("no functions were evaluated: empty coverage data, or --only matched nothing")
    found = tuple(
        f"{path}:{f.line}: {f.name} CRAP {f.crap:.1f} > {run.cfg.crap_max} "
        f"(complexity {f.complexity}, coverage {f.coverage:.0%})"
        for path, f in result.offenders
    )
    summary = f"clean: {result.evaluated} function(s) checked, {len(found)} over CRAP {run.cfg.crap_max}"
    return GateResult("clean", not found, summary, found, {"functions": result.evaluated, "over": len(found)})


def _harden(run: Run) -> GateResult:
    cfg = run.cfg
    tool = languages.get(cfg.language).mutation
    _trusted(run, [tool.artifact])
    m = tool.read(read_artifact(run.art, tool.artifact, tool.how))
    ok = m.pct >= cfg.mutation_min
    summary = f"mutation score {m.pct:.1f}% {'>=' if ok else '<'} {cfg.mutation_min}%"
    return GateResult("harden", ok, summary, tuple(m.survivors), {"score": m.pct, "caught": m.caught, "total": m.total})


def _exclusions(run: Run) -> GateResult:
    pragmas = exclusions.pragmas(run.source, run.cfg.language, run.scope)
    configured = languages.get(run.cfg.language).config_excludes(run.source)
    ok = len(pragmas) <= run.policy.max_exclusions and (run.policy.allow_config_excludes or not configured)
    summary = (
        f"exclusions: {len(pragmas)} comment(s) (budget {run.policy.max_exclusions}), "
        f"{len(configured)} config exclude(s)"
    )
    stats = {"comments": len(pragmas), "config": len(configured)}
    return GateResult("exclusions", ok, summary, tuple(pragmas + configured), stats)


def _spec(run: Run) -> GateResult:
    path = run.feature or run.root / "spec.feature"
    problems = spec.check(path, run.root)
    count = len(spec.parse(path.read_text()).scenarios)
    summary = f"spec: {count} scenario(s), {len(problems)} problem(s)"
    return GateResult("spec", not problems, summary, tuple(problems), {"scenarios": count, "problems": len(problems)})


def _check(run: Run) -> list[GateResult]:
    skipped = GateResult("arch", not run.policy.require_arch, "arch: skipped (no layers configured)")
    return [_arch(run) if run.cfg.layers else skipped, _clean(run), _exclusions(run)]


GATES: dict[str, Callable[[Run], list[GateResult]]] = {
    "arch": lambda run: [_arch(run)],
    "clean": lambda run: [_clean(run)],
    "harden": lambda run: [_harden(run)],
    "exclusions": lambda run: [_exclusions(run)],
    "spec": lambda run: [_spec(run)],
    "check": _check,
}
COMMANDS = ("init", "stamp", "pin", "run", "diagram")
SandboxFactory = Callable[[Path, Config, Policy], Sandbox]
MAKE_SANDBOX: SandboxFactory = backends.gate_sandbox


OPTIONS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("--only", {"action": "append", "metavar": "PATH[:LO-HI]", "help": "limit to a file, directory/ or line range"}),
    ("--artifacts", {"type": Path, "metavar": "DIR", "help": "where artifacts are read from (default: ROOT)"}),
    ("--source", {"type": Path, "metavar": "DIR", "help": "git checkout the artifacts come from (default: ROOT)"}),
    ("--policy", {"type": Path, "metavar": "FILE", "help": "policy file (default: ~/.config/gauntlet/policy.toml)"}),
    ("--json", {"type": Path, "metavar": "FILE", "help": "also write the gate results as JSON"}),
    ("--feature", {"type": Path, "metavar": "FILE", "help": "spec: the Gherkin file (default: ROOT/spec.feature)"}),
    ("--report", {"type": Path, "metavar": "FILE", "help": "also write an EVIDENCE.md report"}),
    ("--out", {"type": Path, "metavar": "DIR", "help": "run: where artifacts are written (default: ROOT/.gauntlet)"}),
    ("--sandbox", {"choices": SANDBOXES, "help": "run: where project code runs (default: the policy's, else local)"}),
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gauntlet")
    parser.add_argument("--version", action="version", version=f"gauntlet {version('gauntlet-core')}")
    parser.add_argument("gate", choices=[*GATES, *COMMANDS])
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    for flag, kwargs in OPTIONS:
        parser.add_argument(flag, **kwargs)
    return parser


def _emit(results: list[GateResult]) -> int:
    for r in results:
        for line in r.findings:
            print(line)
        print(r.summary)
    return 0 if all(r.ok for r in results) else 1


def _fingerprint(run: Run) -> str:
    try:
        return provenance.fingerprint(run.source, provenance.excluded(run.art, run.source, ()))
    except ValueError:
        return "unavailable (not a git repository)"


def _evidence(run: Run, results: list[GateResult], command: str) -> str:
    return report.render(
        results,
        language=run.cfg.language,
        fingerprint=_fingerprint(run),
        config_sha256=hashlib.sha256((run.root / "gauntlet.toml").read_bytes()).hexdigest(),
        policy=run.policy,
        created=datetime.now(UTC).isoformat(timespec="seconds"),
        command=command,
    )


def _write_outputs(run: Run, args: argparse.Namespace, results: list[GateResult]) -> None:
    if args.json:
        args.json.write_text(json.dumps([asdict(r) for r in results], indent=2) + "\n")
    if args.report:
        args.report.write_text(_evidence(run, results, f"gauntlet {args.gate} {args.root}"))


def _stamp(run: Run) -> int:
    expected = languages.get(run.cfg.language).artifacts
    names = [n for n in expected if (run.art / n).is_file()]
    if not names:
        raise FileNotFoundError(f"no artifacts to stamp in {run.art}: expected some of {', '.join(expected)}")
    provenance.stamp(run.art, run.source, names)
    print(f"stamped {', '.join(names)}")
    return 0


def _notice(pol: Policy) -> None:
    if pol.sandbox == "local":
        print(
            'note: project code runs on this machine; for isolation set sandbox = "openshell" in the policy '
            "or pass --sandbox openshell",
            file=sys.stderr,
        )


def _run_pipeline(run: Run) -> list[GateResult]:
    _notice(run.policy)
    names = runner.produce(run.source, run.cfg, run.art, lambda project: MAKE_SANDBOX(project, run.cfg, run.policy))
    print(f"produced {', '.join(names)}")
    return [*_check(run), _harden(run)]


def _pin(args: argparse.Namespace, pol: Policy) -> int:
    target = args.policy or policy.default_path()
    policy.pin(pol, args.root / "gauntlet.toml", target)
    print(f"pinned {args.root / 'gauntlet.toml'} in {target}")
    return 0


def _flagged(pol: Policy, sandbox: str | None) -> Policy:
    """The flag beats the policy's sandbox for this run only (it is never written back by `pin`)."""
    return replace(pol, sandbox=sandbox or pol.sandbox)


def _build_run(args: argparse.Namespace, pol: Policy) -> Run:
    config_path = args.root / "gauntlet.toml"
    raw = load(config_path)
    policy.check_pin(pol, config_path)
    last_run = args.root / ".gauntlet"
    # `stamp` binds the artifacts you just produced, so it must never default to an old run's results.
    use_last = args.gate == "run" or (args.gate != "stamp" and (last_run / provenance.MANIFEST).is_file())
    art = args.artifacts or args.out or (last_run if use_last else args.root)
    scope = parse(args.only or [])
    pol = _flagged(pol, args.sandbox)
    return Run(args.root, art, args.source or args.root, policy.apply(raw, pol), scope, pol, args.feature)


def _init(args: argparse.Namespace) -> int:
    path = scaffold.write_config(args.root)
    print(f"wrote {path}")
    print("next: gauntlet run . --report EVIDENCE.md   (see docs/tutorial.md)")
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    if args.gate == "init":
        return _init(args)
    pol = policy.load(args.policy, missing_ok=args.gate == "pin")
    if args.gate == "pin":
        load(args.root / "gauntlet.toml")
        return _pin(args, pol)
    run = _build_run(args, pol)
    if args.gate == "stamp":
        return _stamp(run)
    if args.gate == "diagram":
        print(diagram.render(run.cfg.layers, _arch_result(run).edges), end="")
        return 0
    results = _run_pipeline(run) if args.gate == "run" else GATES[args.gate](run)
    code = _emit(results)
    _write_outputs(run, args, results)
    return code


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (OSError, GauntletError) as e:
        print(f"gauntlet: {e}", file=sys.stderr)
    except KeyError as e:  # an artifact without a field its reader needs
        print(f"gauntlet: malformed input, missing {e}", file=sys.stderr)
    except (ValueError, TypeError) as e:  # an artifact the reader cannot parse (json.JSONDecodeError is a ValueError)
        print(f"gauntlet: malformed input: {e}", file=sys.stderr)
    return 2
