"""Produce gate artifacts by running fixed, pinned commands inside a sandbox on a private snapshot of the repo.

Nothing the repository contains chooses what runs: commands, tool versions and output names are defined here.
Target code (its tests, mutation runs) executes only in the sandbox; its outputs are copied out and stamped on the host.
"""

import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gauntlet.config import Config
from gauntlet.provenance import excluded, fingerprint, stamp
from gauntlet.safefs import MAX_ARTIFACT_BYTES
from gauntlet.sandbox import ExecResult, Sandbox
from gauntlet.snapshot import snapshot

OUT_DIR = ".gauntlet-out"
IN_SANDBOX = f"/project/{OUT_DIR}"
GOBIN = f"{IN_SANDBOX}/bin"
UV = ("uv", "run", "--project", "/project")
PYTEST_COV = "pytest-cov==7.1.0"
MUTMUT = "mutmut==3.8.0"
C8 = "c8@10.1.3"
GREMLINS = "github.com/go-gremlins/gremlins/cmd/gremlins@v0.6.0"
LIST_FORMAT = '{{.ImportPath}} {{join .Imports " "}}'
PATH_OK = re.compile(r"^(\.|[A-Za-z0-9_][A-Za-z0-9_./-]*)$")
PACKAGE_OK = re.compile(r"^\./[A-Za-z0-9_./-]*(\.\.\.)?$")


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    capture: str | None = None  # write the step's stdout to this artifact
    timeout: int = 1800
    must_pass: bool = True
    env: tuple[tuple[str, str], ...] = ()


def _safe_path(value: str) -> str:
    if not PATH_OK.match(value) or ".." in value.split("/"):
        raise ValueError(f"unsafe path {value!r}")
    return value


def _safe_package(value: str) -> str:
    if not PACKAGE_OK.match(value) or ".." in value.replace("...", "").split("/"):
        raise ValueError(f"unsafe package pattern {value!r}")
    return value


def _python_steps(cfg: Config) -> list[Step]:
    cov = _safe_path(cfg.src)
    report = f"--cov-report=json:{IN_SANDBOX}/coverage.json"
    return [
        Step(
            "tests", (*UV, "--with", PYTEST_COV, "pytest", "-q", f"--cov={cov}", "--cov-branch", report), timeout=3600
        ),
        Step("mutation", (*UV, "--with", MUTMUT, "mutmut", "run"), timeout=7200, must_pass=False),
        Step("mutation-results", (*UV, "--with", MUTMUT, "mutmut", "results", "--all", "true"), "mutmut-results.txt"),
    ]


def _excludes(snap: Path, mutation_dir: str, only: tuple[str, ...]) -> list[str]:
    if not only:
        return []
    keep = {_safe_path(f) for f in only}
    files = sorted(p.relative_to(snap / mutation_dir).as_posix() for p in (snap / mutation_dir).rglob("*.go"))
    return [arg for f in files if f not in keep for arg in ("-E", f"^{re.escape(f)}$")]


def _go_steps(cfg: Config, snap: Path) -> list[Step]:
    packages = tuple(_safe_package(p) for p in cfg.packages)
    mutation_dir = _safe_path(cfg.mutation_dir or ".")
    env = (("GOBIN", GOBIN), ("GOFLAGS", "-buildvcs=false"))
    profile = f"{IN_SANDBOX}/cover.out"
    return [
        Step("install-gremlins", ("go", "install", GREMLINS), env=env),
        Step("tests", ("go", "test", "-count=1", f"-coverprofile={profile}", *packages), timeout=3600, env=env),
        Step("imports", ("go", "list", "-e", "-f", LIST_FORMAT, *packages), "imports.txt", env=env),
        Step(
            "mutation",
            (
                f"{GOBIN}/gremlins",
                "unleash",
                *_excludes(snap, mutation_dir, cfg.mutate_only),
                "-o",
                f"{IN_SANDBOX}/mutation.json",
                mutation_dir,
            ),
            timeout=7200,
            must_pass=False,
            env=env,
        ),
    ]


def _js_steps() -> list[Step]:
    report = f"--reports-dir={IN_SANDBOX}"
    return [
        Step("install", ("npm", "ci", "--ignore-scripts")),  # lockfile only; dependency scripts never run
        Step("tests", ("npx", "--yes", C8, "--reporter=lcovonly", report, "npm", "test"), timeout=3600),
    ]


COPY_REPORT = 'cp "$1"/results/*/coverage.cobertura.xml "$1"/coverage.cobertura.xml'  # one test project per run


def _dotnet_steps() -> list[Step]:
    # coverlet.collector comes from the test project's own references; an empty RunSettingsFilePath keeps a repo's
    # .runsettings (and the exclusions it could carry) out. XDG_RUNTIME_DIR: .NET named mutexes fail for a uid with
    # no passwd entry without it.
    env = (("XDG_RUNTIME_DIR", "/tmp"), ("DOTNET_CLI_TELEMETRY_OPTOUT", "1"), ("DOTNET_NOLOGO", "1"))
    results = f"{IN_SANDBOX}/results"
    return [
        Step(
            "tests",
            ("dotnet", "test", "--collect", "XPlat Code Coverage", "--results-directory", results)
            + ("-p:RunSettingsFilePath=",),
            timeout=3600,
            env=env,
        ),
        Step("report", ("sh", "-c", COPY_REPORT, "sh", IN_SANDBOX)),
    ]


def steps(cfg: Config, snap: Path) -> list[Step]:
    if cfg.language == "go":
        return _go_steps(cfg, snap)
    if cfg.language == "csharp":
        return _dotnet_steps()
    return _js_steps() if cfg.language == "javascript" else _python_steps(cfg)


FILES = {
    "python": ("coverage.json",),
    "go": ("cover.out", "mutation.json"),
    "javascript": ("lcov.info",),
    "csharp": ("coverage.cobertura.xml",),
}  # artifacts the sandbox writes itself
REQUIRED = {
    "python": ("coverage.json", "mutmut-results.txt"),
    "go": ("cover.out", "imports.txt"),
    "javascript": ("lcov.info",),
    "csharp": ("coverage.cobertura.xml",),
}


def output_tail(done: ExecResult) -> str:
    """The end of what a failed command printed: stderr and stdout, whichever have content."""
    return " | ".join(part for part in (done.stderr.strip(), done.stdout.strip()) if part)[-2000:]


def _run_steps(box: Sandbox, plan: list[Step]) -> dict[str, bytes]:
    captured: dict[str, bytes] = {}
    for step in plan:
        done = box.exec(step.argv, dict(step.env), step.timeout)
        if done.code != 0 and step.must_pass:
            raise ValueError(f"step {step.name!r} failed (exit {done.code}): {output_tail(done)}")
        if step.capture and done.stdout:
            captured[step.capture] = done.stdout.encode()
    return captured


def _read_artifact(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError(f"{path.name} is a symlink")
    data = path.read_bytes() if path.is_file() else None
    if data is not None and len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"{path.name} is {len(data)} bytes, over the {MAX_ARTIFACT_BYTES} byte limit")
    return data


def _collect(snap: Path, language: str, captured: dict[str, bytes]) -> dict[str, bytes]:
    found = dict(captured)
    for name in FILES[language]:
        data = _read_artifact(snap / OUT_DIR / name)
        if data is not None:
            found[name] = data
    for name, data in captured.items():
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError(f"{name} is {len(data)} bytes, over the {MAX_ARTIFACT_BYTES} byte limit")
    missing = [n for n in REQUIRED[language] if n not in found]
    if missing:
        raise ValueError(f"the sandbox did not produce {', '.join(missing)}")
    return found


def produce(source: Path, cfg: Config, out: Path, make_sandbox: Callable[[Path], Sandbox]) -> list[str]:
    """Run the pipeline in a sandbox; leave stamped artifacts in `out`. Returns the artifact names."""
    skip = excluded(out, source, ())
    before = fingerprint(source, skip)
    with tempfile.TemporaryDirectory(prefix="gauntlet-") as tmp:
        snap = Path(tmp) / "project"
        snapshot(source, snap)
        (snap / OUT_DIR).mkdir()
        box = make_sandbox(snap)
        box.ensure()
        try:
            captured = _run_steps(box, steps(cfg, snap))
        finally:
            box.remove()
        found = _collect(snap, cfg.language, captured)
    if fingerprint(source, skip) != before:
        raise ValueError("source changed while the gauntlet ran; rerun it")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in found.items():
        (out / name).write_bytes(data)
    stamp(out, source, sorted(found))
    return sorted(found)
