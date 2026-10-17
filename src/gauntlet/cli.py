import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
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
    golang,
    harden,
    languages,
    linecov,
    loop,
    policy,
    provenance,
    report,
    runner,
    scaffold,
    spec,
)
from gauntlet.config import Config, load
from gauntlet.policy import Policy
from gauntlet.results import GateResult
from gauntlet.safefs import read_text
from gauntlet.sandbox import Sandbox
from gauntlet.scope import Scope, parse

IMPORTS_HOW = "go list -e -f '{{.ImportPath}} {{join .Imports \" \"}}' ./..."
MUTMUT_HOW = "mutmut run && mutmut results --all true > mutmut-results.txt (or: gauntlet run)"
ARTIFACTS = {
    "python": ("coverage.json", "mutmut-results.txt"),
    "go": ("cover.out", "imports.txt", "mutation.json"),
    "javascript": ("lcov.info",),
    "csharp": ("coverage.cobertura.xml",),
    "java": ("jacoco.xml",),
    "rust": ("lcov.info",),
    "cpp": ("lcov.info",),
    "dart": ("lcov.info",),
}


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
        raise ValueError("no layers configured: add [layers] order to gauntlet.toml")
    if cfg.language not in ("python", "go"):
        raise ValueError(f"arch has no import reader for {cfg.language} yet")
    if cfg.language == "go":
        _trusted(run, ["imports.txt"])
        result = golang.arch_check(golang.read(run.art, "imports.txt", IMPORTS_HOW), cfg.layers)
    else:
        result = arch.check(run.root / cfg.src, cfg.layers)
    if result.modules == 0:
        raise ValueError("no module belongs to any configured layer; check [layers] and src")
    return result


def _arch(run: Run) -> GateResult:
    result = _arch_result(run)
    found = tuple(
        f"{v.path}:{v.line}: {v.source} imports outer layer {v.target}"
        if v.line
        else f"{v.path}: {v.source} imports outer layer {v.target}"
        for v in result.violations
    )
    summary = f"arch: {result.modules} module(s) checked, {len(found)} violation(s)"
    return GateResult("arch", not found, summary, found, {"modules": result.modules, "violations": len(found)})


def _clean_result(run: Run) -> clean.CleanResult:
    language = languages.get(run.cfg.language)
    _trusted(run, [language.coverage_file])
    text = golang.read(
        run.art, language.coverage_file, f"gauntlet run, or your test runner's {language.coverage_format} report"
    )
    lines = linecov.parse(language.coverage_format, text)
    return clean.check(run.root, lines, language, run.cfg.crap_max, run.scope)


def _clean(run: Run) -> GateResult:
    result = _clean_result(run)
    if result.evaluated == 0:
        raise ValueError("no functions were evaluated: empty coverage data, or --only matched nothing")
    found = tuple(
        f"{path}:{f.line}: {f.name} CRAP {f.crap:.1f} > {run.cfg.crap_max} "
        f"(complexity {f.complexity}, coverage {f.coverage:.0%})"
        for path, f in result.offenders
    )
    summary = f"clean: {result.evaluated} function(s) checked, {len(found)} over CRAP {run.cfg.crap_max}"
    return GateResult("clean", not found, summary, found, {"functions": result.evaluated, "over": len(found)})


def _harden_or_skip(run: Run) -> GateResult:
    """For `run` and `loop`: no wired mutation tool is a failure, unless the operator's policy accepts it."""
    if languages.get(run.cfg.language).mutation:
        return _harden(run)
    ok = run.policy.allow_skipped_gates
    note = "" if ok else " (set allow_skipped_gates = true in your policy to accept)"
    return GateResult("harden", ok, f"harden: SKIPPED, no mutation tool is wired for {run.cfg.language} yet{note}")


def _harden(run: Run) -> GateResult:
    cfg = run.cfg
    if not languages.get(cfg.language).mutation:
        raise ValueError(f"harden is not available for {cfg.language} yet")
    if cfg.language == "go":
        _trusted(run, ["mutation.json"])
        text = golang.read(run.art, "mutation.json", "gremlins unleash -o mutation.json .")
        m = golang.harden_check(text, run.scope, cfg.mutation_dir)
    else:
        _trusted(run, ["mutmut-results.txt"])
        m = harden.check(golang.read(run.art, "mutmut-results.txt", MUTMUT_HOW))
    ok = m.pct >= cfg.mutation_min
    summary = f"mutation score {m.pct:.1f}% {'>=' if ok else '<'} {cfg.mutation_min}%"
    return GateResult("harden", ok, summary, tuple(m.survivors), {"score": m.pct, "caught": m.caught, "total": m.total})


def _exclusions(run: Run) -> GateResult:
    pragmas = exclusions.pragmas(run.source, run.cfg.language, run.scope)
    if run.cfg.language == "python":
        configured = exclusions.config_excludes(run.source)
    else:
        configured = exclusions.config_hints(run.source, run.cfg.language)
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
    skipped = GateResult("arch", True, "arch: skipped (no layers configured)")
    return [_arch(run) if run.cfg.layers else skipped, _clean(run), _exclusions(run)]


GATES: dict[str, Callable[[Run], list[GateResult]]] = {
    "arch": lambda run: [_arch(run)],
    "clean": lambda run: [_clean(run)],
    "harden": lambda run: [_harden(run)],
    "exclusions": lambda run: [_exclusions(run)],
    "spec": lambda run: [_spec(run)],
    "check": _check,
}
COMMANDS = ("init", "stamp", "pin", "run", "diagram", "loop")
SandboxFactory = Callable[[Path, Config, Policy], Sandbox]
MAKE_SANDBOX: SandboxFactory = backends.gate_sandbox
MAKE_AGENT_SANDBOX: SandboxFactory = backends.agent_sandbox


OPTIONS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("--only", {"action": "append", "metavar": "PATH[:LO-HI]", "help": "limit to a file, directory/ or line range"}),
    ("--artifacts", {"type": Path, "metavar": "DIR", "help": "where artifacts are read from (default: ROOT)"}),
    ("--source", {"type": Path, "metavar": "DIR", "help": "git checkout the artifacts come from (default: ROOT)"}),
    ("--policy", {"type": Path, "metavar": "FILE", "help": "policy file (default: ~/.config/gauntlet/policy.toml)"}),
    ("--json", {"type": Path, "metavar": "FILE", "help": "also write the gate results as JSON"}),
    ("--feature", {"type": Path, "metavar": "FILE", "help": "spec: the Gherkin file (default: ROOT/spec.feature)"}),
    ("--requirement", {"type": str, "metavar": "TEXT", "help": "loop: what to build (the Specifier writes a spec)"}),
    ("--spec", {"type": Path, "metavar": "FILE", "help": "loop: the approved spec to implement"}),
    ("--report", {"type": Path, "metavar": "FILE", "help": "also write an EVIDENCE.md report"}),
    ("--out", {"type": Path, "metavar": "DIR", "help": "run: where artifacts are written (default: ROOT/.gauntlet)"}),
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gauntlet")
    parser.add_argument("--version", action="version", version=f"gauntlet {version('gauntlet')}")
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


def _write_outputs(run: Run, args: argparse.Namespace, results: list[GateResult]) -> None:
    if args.json:
        args.json.write_text(json.dumps([r.as_dict() for r in results], indent=2) + "\n")
    if args.report:
        config_hash = hashlib.sha256((run.root / "gauntlet.toml").read_bytes()).hexdigest()
        args.report.write_text(
            report.render(
                results,
                language=run.cfg.language,
                fingerprint=_fingerprint(run),
                config_sha256=config_hash,
                policy=run.policy,
                created=datetime.now(UTC).isoformat(timespec="seconds"),
                command=f"gauntlet {args.gate} {args.root}",
            )
        )


def _stamp(run: Run) -> int:
    names = [n for n in ARTIFACTS[run.cfg.language] if (run.art / n).is_file()]
    if not names:
        raise FileNotFoundError(
            f"no artifacts to stamp in {run.art}: expected some of {', '.join(ARTIFACTS[run.cfg.language])}"
        )
    provenance.stamp(run.art, run.source, names)
    print(f"stamped {', '.join(names)}")
    return 0


def _run_pipeline(run: Run) -> list[GateResult]:
    names = runner.produce(run.source, run.cfg, run.art, lambda project: MAKE_SANDBOX(project, run.cfg, run.policy))
    print(f"produced {', '.join(names)}")
    return [*_check(run), _harden_or_skip(run)]


def _evaluator(run: Run, workspace: Path, out: Path, approved: Path) -> Callable[[], list[GateResult]]:
    def evaluate() -> list[GateResult]:
        sub = replace(run, root=workspace, source=workspace, art=out / "artifacts", feature=approved)
        runner.produce(workspace, run.cfg, sub.art, lambda project: MAKE_SANDBOX(project, run.cfg, run.policy))
        return [*_check(sub), _harden_or_skip(sub), _spec(sub)]

    return evaluate


def _loop_finish(run: Run, args: argparse.Namespace, workspace: Path, out: Path, result: loop.LoopResult) -> int:
    diff = loop.patch(workspace)
    (out / "loop.patch").write_text(diff)
    sub = replace(run, source=workspace, art=out / "artifacts")
    config_hash = hashlib.sha256((run.root / "gauntlet.toml").read_bytes()).hexdigest()
    command = f"gauntlet loop {args.root} --spec {args.spec}"
    created = datetime.now(UTC).isoformat(timespec="seconds")
    text = report.render(
        result.results,
        language=run.cfg.language,
        fingerprint=_fingerprint(sub),
        config_sha256=config_hash,
        policy=run.policy,
        created=created,
        command=command,
    )
    (out / "EVIDENCE.md").write_text(text)
    code = _emit(result.results)
    print(f"fixer rounds: {result.rounds}; patch: {out / 'loop.patch'}; evidence: {out / 'EVIDENCE.md'}")
    if control := loop.control_files(diff):
        print(f"warning: the patch touches control files: {', '.join(control)} (review these first)")
    return code if result.ok else 1


def _loop_stages(run: Run, args: argparse.Namespace, agent: loop.Agent, workspace: Path, out: Path) -> int:
    roles = loop.load_roles()
    if args.spec is None:
        written = out / "spec.feature"
        written.write_text(loop.specify(agent, roles, args.requirement, workspace))
        print(f"spec written to {written}; review it, then rerun with --spec {written}")
        return 3
    approved = read_text(args.spec, spec.MAX_SPEC_BYTES)
    result = loop.implement(agent, roles, approved, _evaluator(run, workspace, out, args.spec), run.policy.max_rounds)
    return _loop_finish(run, args, workspace, out, result)


def _loop(run: Run, args: argparse.Namespace) -> int:
    if not run.policy.agent_command:
        raise ValueError(loop.NO_AGENT)
    if not (args.requirement or args.spec):
        raise ValueError("give --requirement (to write a spec) or --spec (an approved spec to implement)")
    out: Path = args.out or run.root / ".gauntlet-loop"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gauntlet-loop-") as tmp:
        workspace = loop.prepare_workspace(run.source, Path(tmp) / "ws")
        box = MAKE_AGENT_SANDBOX(workspace, run.cfg, run.policy)
        agent = loop.Agent(box, run.policy.agent_command, run.policy.agent_env, run.policy.agent_timeout)
        box.ensure()
        try:
            return _loop_stages(run, args, agent, workspace, out)
        finally:
            box.remove()


def _pin(args: argparse.Namespace, pol: Policy) -> int:
    target = args.policy or policy.default_path()
    policy.pin(pol, args.root / "gauntlet.toml", target)
    print(f"pinned {args.root / 'gauntlet.toml'} in {target}")
    return 0


def _build_run(args: argparse.Namespace, pol: Policy) -> Run:
    config_path = args.root / "gauntlet.toml"
    raw = load(config_path)
    policy.check_pin(pol, config_path)
    last_run = args.root / ".gauntlet"
    # `stamp` binds the artifacts you just produced, so it must never default to an old run's results.
    use_last = args.gate == "run" or (args.gate != "stamp" and (last_run / provenance.MANIFEST).is_file())
    art = args.artifacts or args.out or (last_run if use_last else args.root)
    scope = parse(args.only or [])
    return Run(args.root, art, args.source or args.root, policy.apply(raw, pol), scope, pol, args.feature)


def _init(args: argparse.Namespace) -> int:
    path = scaffold.write_config(args.root)
    print(f"wrote {path}")
    print("next: gauntlet run .   (needs Canonical Workshop; see the README), then read EVIDENCE with --report")
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
    if args.gate == "loop":
        return _loop(run, args)
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
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"gauntlet: {e if not isinstance(e, KeyError) else f'malformed input, missing {e}'}", file=sys.stderr)
        return 2
