"""Produce gate artifacts by running fixed, pinned commands inside a sandbox on a private snapshot of the repo.

Nothing the repository contains chooses what runs: commands, tool versions and output names are defined here.
Target code (its tests, mutation runs) executes only in the sandbox; its outputs are copied out and stamped on the host.
"""

import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from gauntlet import languages, mutation
from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.provenance import excluded, fingerprint, stamp
from gauntlet.safefs import MAX_ARTIFACT_BYTES
from gauntlet.sandbox import ExecResult, Sandbox
from gauntlet.snapshot import snapshot

OUT_DIR = ".gauntlet-out"
IN_SANDBOX = f"/project/{OUT_DIR}"
GOBIN = f"{IN_SANDBOX}/bin"
UV = ("uv", "run", "--project", "/project")
WRITE_FILE = 'printf %s "$1" > "$2"'  # writes $1 to the file $2
PYTEST_COV = "pytest-cov==7.1.0"
MUTMUT = "mutmut==3.8.0"
C8 = "c8@10.1.3"
STRYKER = "@stryker-mutator/core@9.6.1"  # the command test runner is built in: no plugins to install
JACOCO = "org.jacoco:jacoco-maven-plugin:0.8.12"
PITEST = "org.pitest:pitest-maven:1.17.4"
PIT_JUNIT5 = "org.pitest:pitest-junit5-plugin:1.2.1"
PIT_REPORT = "target/pit-reports/mutations.xml"
DEPENDENCY = "org.apache.maven.plugins:maven-dependency-plugin:3.8.1"
LLVM_COV = "0.6.21"
CARGO_MUTANTS = "27.1.0"
MUTANTS_OUT = f"{IN_SANDBOX}/mutants"
CARGO_TOOLS = f"{IN_SANDBOX}/cargo"
PIP_URL = (
    "https://files.pythonhosted.org/packages/ef/7d/500c9ad20238fcfcb4cb9243eede163594d7020ce87bd9610c9e02771876"
    "/pip-24.3.1-py3-none-any.whl"
)
PIP_SHA256 = "3790624780082365f47549d032f3770eeb2b1e8bd1f7b2e02dace1afa361b4ed"
DART_COVERAGE = "1.15.0"
STRYKER_NET = "4.8.1"
STRYKER_CONFIG = f"{IN_SANDBOX}/stryker-config.json"
GREMLINS = "github.com/go-gremlins/gremlins/cmd/gremlins@v0.6.0"
LIST_FORMAT = '{{.ImportPath}} {{join .Imports " "}}'
MULL_URL = (  # built for clang 21.1.8, the exact release of the cpp-clang image
    "https://github.com/mull-project/mull/releases/download/0.34.0/Mull-21-0.34.0-LLVM-21.1.8-ubuntu-amd64-26.04.deb"
)
MULL_SHA256 = "6b942ec5727f8ab5e06d7885d130a502dd0ad41c742814e6cbfdac3658f9a080"
MULL = f"{IN_SANDBOX}/mull"
MULL_CONFIG = f"{IN_SANDBOX}/mull.yml"
MULL_REPORTS = f"{IN_SANDBOX}/mull-reports"
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
        raise GauntletError(f"unsafe path {value!r}")
    return value


def _safe_package(value: str) -> str:
    if not PACKAGE_OK.match(value) or ".." in value.replace("...", "").split("/"):
        raise GauntletError(f"unsafe package pattern {value!r}")
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


def _stryker_config() -> str:
    """Stryker's settings, ours alone (passed by path, so a repo's stryker.conf.* is never read). What gets mutated
    follows the language row: its suffixes, minus node_modules, our output and the top-level test directories."""
    suffixes = ",".join(s.lstrip(".") for s in languages.TABLE["javascript"].suffixes)
    skip = ("**/node_modules", OUT_DIR, "tests", "test", "__tests__")
    return json.dumps(
        {
            "testRunner": "command",
            "commandRunner": {"command": "npm test"},
            "coverageAnalysis": "off",
            "reporters": ["json"],
            "jsonReporter": {"fileName": f"{IN_SANDBOX}/stryker.json"},
            "mutate": [f"**/*.{{{suffixes}}}", *(f"!{d}/**" for d in skip)],
            "ignorePatterns": [OUT_DIR],
            "tempDirName": f"{IN_SANDBOX}/stryker-tmp",
        }
    )


def _js_steps() -> list[Step]:
    report = f"--reports-dir={IN_SANDBOX}"
    tool, conf = f"{IN_SANDBOX}/stryker", f"{IN_SANDBOX}/stryker.conf.json"
    install = ("npm", "install", "--prefix", tool, "--ignore-scripts", "--no-audit", "--no-fund", "--no-save", STRYKER)
    return [
        Step("install", ("npm", "ci", "--ignore-scripts")),  # lockfile only; dependency scripts never run
        Step("tests", ("npx", "--yes", C8, "--reporter=lcovonly", report, "npm", "test"), timeout=3600),
        Step("install-stryker", install),
        Step("stryker-config", ("sh", "-c", WRITE_FILE, "sh", _stryker_config(), conf)),
        Step("mutation", ("node", f"{tool}/node_modules/.bin/stryker", "run", conf), timeout=7200, must_pass=False),
    ]


COPY_REPORT = 'cp "$1"/results/*/coverage.cobertura.xml "$1"/coverage.cobertura.xml'  # one test project per run


def _stryker_steps(env: tuple[tuple[str, str], ...]) -> list[Step]:
    """Stryker.NET reads only our own config file, so a repo's stryker-config.json cannot narrow the mutation."""
    tool = f"{IN_SANDBOX}/tools"
    out = f"{IN_SANDBOX}/stryker"
    write = 'echo \'{"stryker-config":{}}\' > "$1"'
    run = (f"{tool}/dotnet-stryker", "--config-file", STRYKER_CONFIG, "--mutate", "**/*.cs")
    install = ("dotnet", "tool", "install", "--tool-path", tool, "dotnet-stryker", "--version", STRYKER_NET)
    return [
        Step("install-stryker", install, env=env),
        Step("stryker-config", ("sh", "-c", write, "sh", STRYKER_CONFIG)),
        Step("mutation", (*run, "--reporter", "json", "--output", out), timeout=7200, must_pass=False, env=env),
        Step("mutation-report", ("cp", f"{out}/reports/mutation-report.json", f"{IN_SANDBOX}/stryker-report.json"),
             must_pass=False),
    ]  # fmt: skip


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
        *_stryker_steps(env),
    ]


def _java_steps() -> list[Step]:
    m2 = f"{IN_SANDBOX}/m2"
    repo = f"-Dmaven.repo.local={m2}"  # no writable HOME for every uid
    junit5 = f"{m2}/org/pitest/pitest-junit5-plugin/1.2.1/pitest-junit5-plugin-1.2.1.jar"
    # PIT is called by its goal, so the pom cannot add the JUnit 5 plugin: fetch the jar and put it on the classpath.
    # Properties stand where the pom is silent; a <configuration> in the pom would win (the exclusions gate reports it).
    pit = (
        f"-DoutputFormats=XML -DtimestampedReports=false -Dmutators=DEFAULTS -DadditionalClasspathElements={junit5}"
        " -DexcludedClasses= -DexcludedMethods= -DexcludedTestClasses= -DwithHistory=false -DavoidCallsTo="
        " -Dfeatures=-FANN"  # -FANN: an @DoNotMutate annotation hides nothing from the gate
    ).split()
    mvn = ("mvn", "-B", "-ntp", repo)
    return [
        Step("tests", (*mvn, f"{JACOCO}:prepare-agent", "test", f"{JACOCO}:report"), timeout=3600),
        Step("collect", ("cp", "target/site/jacoco/jacoco.xml", f"{IN_SANDBOX}/jacoco.xml")),
        Step("pit-junit5", (*mvn, f"{DEPENDENCY}:get", f"-Dartifact={PIT_JUNIT5}", "-Dtransitive=false")),
        Step("mutation", (*mvn, f"{PITEST}:mutationCoverage", *pit), timeout=7200, must_pass=False),
        Step("mutation-collect", ("cp", PIT_REPORT, f"{IN_SANDBOX}/mutations.xml"), must_pass=False),
    ]


def _cargo_install(crate: str, version: str) -> tuple[str, ...]:
    return ("cargo", "install", "--locked", "--version", version, crate, "--root", CARGO_TOOLS)


def _rust_steps() -> list[Step]:
    cov = (
        f"{CARGO_TOOLS}/bin/cargo-llvm-cov",
        "llvm-cov",
        "--locked",
        "--lcov",
        "--output-path",
        f"{IN_SANDBOX}/lcov.info",
    )
    mutants = (f"{CARGO_TOOLS}/bin/cargo-mutants", "mutants", "--no-config", "--output", MUTANTS_OUT)
    report = ("cp", f"{MUTANTS_OUT}/mutants.out/outcomes.json", f"{IN_SANDBOX}/mutants-outcomes.json")
    return [
        Step("llvm-tools", ("rustup", "component", "add", "llvm-tools-preview")),
        Step("install-llvm-cov", _cargo_install("cargo-llvm-cov", LLVM_COV)),
        Step("tests", cov, timeout=3600),
        Step("install-mutants", _cargo_install("cargo-mutants", CARGO_MUTANTS)),
        # --no-config: the repository's .cargo/mutants.toml cannot narrow what is mutated
        Step("mutation", mutants, timeout=7200, must_pass=False),
        Step("mutation-report", report, must_pass=False),
    ]


def _cpp_install() -> str:
    """The image has gcc and python3 but no pip, cmake or gcovr: bootstrap a hash-checked pip, then install the
    hash-locked tools (data/cpp-requirements.txt). `-P` keeps the repository's own modules off sys.path."""
    lock = (files("gauntlet") / "data" / "cpp-requirements.txt").read_text()
    return (
        f"set -eu; D={IN_SANDBOX}; curl -fsSL {PIP_URL} -o $D/pip.whl; "
        f'echo "{PIP_SHA256}  $D/pip.whl" | sha256sum -c -; '
        f"cat > $D/requirements.txt <<'LOCK'\n{lock}LOCK\n"
        "PYTHONPATH=$D/pip.whl python3 -P -m pip install -q --no-cache-dir --only-binary=:all: --require-hashes "
        "--no-deps --target $D/py -r $D/requirements.txt; "
        ": > $D/gcovr.cfg"  # an empty config: the repository's own gcovr.cfg is never read
    )


CPP_FLAGS = tuple(f"-DCMAKE_{kind}_FLAGS=--coverage" for kind in ("C", "CXX", "EXE_LINKER"))
CPP_MUTANTS = f"{IN_SANDBOX}/cppmutants.py"


def _cpp_mutation_steps(env: tuple[tuple[str, str], ...]) -> list[Step]:
    """universalmutator, driven by our own script (gauntlet.cppmutants, shipped as a file): it picks the
    files from the language row, uses the built-in rules only and builds in its own build directory."""
    row = languages.TABLE["cpp"]
    script = (files("gauntlet") / "cppmutants.py").read_text()
    args = (IN_SANDBOX, f"{IN_SANDBOX}/{mutation.TOOLS['cpp'].artifact}", ",".join(row.suffixes), row.tests)
    return [
        Step("mutation-script", ("sh", "-c", WRITE_FILE, "sh", script, CPP_MUTANTS)),
        Step("mutation", ("python3", "-P", CPP_MUTANTS, "/project", *args, *CPP_FLAGS),
             timeout=7200, must_pass=False, env=env),
    ]  # fmt: skip


def _cpp_steps() -> list[Step]:
    py, build = f"{IN_SANDBOX}/py", f"{IN_SANDBOX}/build"
    env = (("PYTHONPATH", py),)
    return [
        Step("install", ("sh", "-c", _cpp_install())),
        Step("configure", (f"{py}/bin/cmake", "-S", ".", "-B", build, "-DCMAKE_BUILD_TYPE=Debug", *CPP_FLAGS), env=env),
        Step("build", (f"{py}/bin/cmake", "--build", build), timeout=3600, env=env),
        Step("tests", (f"{py}/bin/ctest", "--test-dir", build, "--output-on-failure"), timeout=3600, env=env),
        Step(
            "coverage",
            (
                "python3", "-P", "-m", "gcovr", "--config", f"{IN_SANDBOX}/gcovr.cfg", "--root", "/project",
                "--object-directory", build, "--exclude", rf"^/project/{re.escape(OUT_DIR)}/",
                "--lcov", f"{IN_SANDBOX}/lcov.info",
            ),
            env=env,
        ),
        *_cpp_mutation_steps(env),
    ]  # fmt: skip


def _mull_config() -> str:
    """Mull's settings, ours alone (MULL_CONFIG names this file, so a mull.yml in the repo or above it is never read).
    JSON is YAML. Only project code is mutated: not the top-level test directories, nor our own output."""
    tests = languages.TABLE["cpp-clang"].tests.removeprefix("^")
    return json.dumps(
        {"includePaths": ["^/project/"], "excludePaths": [f"^/project/(?:{tests}|{re.escape(OUT_DIR)}/)"]}
    )


def _cpp_clang_steps() -> list[Step]:
    """Coverage from clang's source-based instrumentation; mutation with Mull, whose clang plugin is fetched by its
    pinned hash and unpacked without root. The helper (data/cpp-clang-driver.txt) finds the test executables through
    `ctest --show-only=json-v1`, so nothing the repository contains chooses what runs."""
    driver = (files("gauntlet") / "data" / "cpp-clang-driver.txt").read_text()
    helper = ("python3", "-I", "-c", driver)
    build, mull_build, profiles = f"{IN_SANDBOX}/build", f"{IN_SANDBOX}/mull-build", f"{IN_SANDBOX}/prof"
    cov = "-fprofile-instr-generate -fcoverage-mapping"
    plugin = f"-O0 -g -grecord-command-line -fpass-plugin={MULL}/usr/lib/mull-ir-frontend-21"
    cmake = ("cmake", "-DCMAKE_C_COMPILER=clang", "-DCMAKE_CXX_COMPILER=clang++", "-DCMAKE_BUILD_TYPE=Debug")
    env = (("MULL_CONFIG", MULL_CONFIG),)

    def configure(where: str, flags: str) -> tuple[str, ...]:
        return (*cmake, "-S", ".", "-B", where, f"-DCMAKE_C_FLAGS={flags}", f"-DCMAKE_CXX_FLAGS={flags}")

    return [
        Step("install-mull", (*helper, "install", MULL_URL, MULL_SHA256, MULL)),
        Step("configure", (*configure(build, cov), f"-DCMAKE_EXE_LINKER_FLAGS={cov}")),
        Step("build", ("cmake", "--build", build), timeout=3600),
        Step(
            "tests",
            ("ctest", "--test-dir", build, "--output-on-failure"),
            timeout=3600,
            env=(("LLVM_PROFILE_FILE", f"{profiles}/%p-%m.profraw"),),
        ),
        Step("coverage", (*helper, "coverage", build, profiles, f"{IN_SANDBOX}/lcov.info")),
        Step("mull-config", ("sh", "-c", WRITE_FILE, "sh", _mull_config(), MULL_CONFIG)),
        Step("mull-configure", configure(mull_build, plugin), env=env),
        Step("mull-build", ("cmake", "--build", mull_build), timeout=3600, env=env),
        Step(
            "mutation",
            (
                *helper,
                "mutate",
                mull_build,
                f"{MULL}/usr/bin/mull-runner-21",
                MULL_REPORTS,
                f"{IN_SANDBOX}/mull-report.json",
            ),
            timeout=7200,
            must_pass=False,
            env=env,
        ),
    ]


def _dart_steps() -> list[Step]:
    raw = f"{IN_SANDBOX}/raw"
    pub = ("dart", "pub", "global")
    return [
        Step("install", ("dart", "pub", "get", "--enforce-lockfile")),  # lockfile only; nothing is re-resolved
        Step("coverage tool", (*pub, "activate", "coverage", DART_COVERAGE)),
        Step("tests", ("dart", "test", f"--coverage={raw}"), timeout=3600),
        Step(
            "report",
            (
                *pub,
                "run",
                "coverage:format_coverage",
                "--lcov",
                f"--in={raw}",
                f"--out={IN_SANDBOX}/lcov.info",
                "--report-on=lib",
                "--report-on=bin",
                "--packages=.dart_tool/package_config.json",
            ),
        ),  # fmt: skip
    ]


BUILDERS: dict[str, Callable[[Config, Path], list[Step]]] = {  # one per row of languages.TABLE
    "python": lambda cfg, snap: _python_steps(cfg),  # noqa: ARG005
    "go": _go_steps,
    "javascript": lambda cfg, snap: _js_steps(),  # noqa: ARG005
    "csharp": lambda cfg, snap: _dotnet_steps(),  # noqa: ARG005
    "java": lambda cfg, snap: _java_steps(),  # noqa: ARG005
    "rust": lambda cfg, snap: _rust_steps(),  # noqa: ARG005
    "cpp": lambda cfg, snap: _cpp_steps(),  # noqa: ARG005
    "cpp-clang": lambda cfg, snap: _cpp_clang_steps(),  # noqa: ARG005
    "dart": lambda cfg, snap: _dart_steps(),  # noqa: ARG005
}


def steps(cfg: Config, snap: Path) -> list[Step]:
    return BUILDERS[cfg.language](cfg, snap)


def output_tail(done: ExecResult) -> str:
    """The end of what a failed command printed: stderr and stdout, whichever have content."""
    return " | ".join(part for part in (done.stderr.strip(), done.stdout.strip()) if part)[-2000:]


INTERMEDIATES = {  # what the copy steps after a mutation run read, as the tool leaves it
    "java": ("target/pit-reports",),
    "csharp": (f"{IN_SANDBOX}/stryker",),
    "rust": (MUTANTS_OUT,),
    "cpp": (f"{IN_SANDBOX}/mutwork", f"{IN_SANDBOX}/mutbuild"),
    "cpp-clang": (MULL_REPORTS,),
}


def _stale(language: str) -> tuple[str, ...]:
    tool = mutation.TOOLS.get(language)
    return (f"{IN_SANDBOX}/{tool.artifact}", *INTERMEDIATES.get(language, ())) if tool else ()


def _clear(box: Sandbox, stale: tuple[str, ...]) -> None:
    removal = box.exec(["rm", "-rf", "--", *stale], {}, 60)
    if removal.code != 0:
        raise GauntletError(f"could not clear the old mutation report: {output_tail(removal)}")


def _run_steps(box: Sandbox, plan: list[Step], stale: tuple[str, ...] = ()) -> dict[str, bytes]:
    """Run the plan. `stale` (the mutation report and the intermediate files the copy steps read) is removed by the
    sandbox itself right before the mutation step: a file the tests left behind can never stand in for the report of a
    mutation run that crashed or timed out, and the host never touches a path the tests could have turned into a
    symlink."""
    captured: dict[str, bytes] = {}
    for step in plan:
        if stale and step.name == "mutation":
            _clear(box, stale)
        done = box.exec(step.argv, dict(step.env), step.timeout)
        if done.code != 0 and step.must_pass:
            raise GauntletError(f"step {step.name!r} failed (exit {done.code}): {output_tail(done)}")
        if step.capture and done.stdout:
            captured[step.capture] = done.stdout.encode()
            _check_size(step.capture, captured[step.capture])
    return captured


def _check_size(name: str, data: bytes) -> None:
    if len(data) > MAX_ARTIFACT_BYTES:
        raise GauntletError(f"{name} is {len(data)} bytes, over the {MAX_ARTIFACT_BYTES} byte limit")


def _read_artifact(path: Path) -> bytes | None:
    if path.is_symlink():
        raise GauntletError(f"{path.name} is a symlink")
    data = path.read_bytes() if path.is_file() else None
    if data is not None:
        _check_size(path.name, data)
    return data


def _written(snap: Path, names: list[str]) -> dict[str, bytes]:
    """The artifacts the sandbox wrote to its output directory."""
    if (snap / OUT_DIR).is_symlink():  # the tests swapped the output directory for a link to somewhere on the host
        raise GauntletError(f"{OUT_DIR} is a symlink")
    found = {name: _read_artifact(snap / OUT_DIR / name) for name in names}
    return {name: data for name, data in found.items() if data is not None}


def _collect(snap: Path, language: str, plan: list[Step], captured: dict[str, bytes]) -> dict[str, bytes]:
    """The row's artifacts: a step's captured stdout, else the file the sandbox wrote. A file never stands in for a
    captured artifact, so the tests cannot forge one by leaving it in the output directory."""
    row = languages.get(language)
    stdout = {step.capture for step in plan}
    found = {**_written(snap, [n for n in row.artifacts if n not in stdout]), **captured}
    missing = [n for n in row.artifacts if n not in row.optional and n not in found]
    if missing:
        raise GauntletError(f"the sandbox did not produce {', '.join(missing)}")
    return found


def produce(source: Path, cfg: Config, out: Path, make_sandbox: Callable[[Path], Sandbox]) -> list[str]:
    """Run the pipeline in a sandbox; leave stamped artifacts in `out`. Returns the artifact names."""
    skip = excluded(out, source, ())
    before = fingerprint(source, skip)
    with tempfile.TemporaryDirectory(prefix="gauntlet-") as tmp:
        snap = Path(tmp) / "project"
        snapshot(source, snap)
        (snap / OUT_DIR).mkdir()
        plan = steps(cfg, snap)
        box = make_sandbox(snap)
        box.ensure()
        try:
            captured = _run_steps(box, plan, _stale(cfg.language))
        finally:
            box.remove()
        found = _collect(snap, cfg.language, plan, captured)
    if fingerprint(source, skip) != before:
        raise GauntletError("source changed while the gauntlet ran; rerun it")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in found.items():
        (out / name).write_bytes(data)
    stamp(out, source, sorted(found))
    return sorted(found)
