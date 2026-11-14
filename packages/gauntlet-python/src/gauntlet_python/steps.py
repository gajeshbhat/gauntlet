"""The fixed, pinned commands that produce the Python artifacts in the sandbox.

The helper scripts run as `python3 -I -c`: isolated mode keeps the working directory (the project) off the import
path, so a project file called `re.py` or `json.py` cannot stand in for the standard library's.
"""

from pathlib import PurePosixPath

from gauntlet.plugin import Step

PYTEST_COV = "pytest-cov==7.1.0"
MUTMUT = "mutmut==3.8.1"
COSMIC_RAY = "cosmic-ray==8.7.0"
# The private copy has no git history, so projects that read their version from git (setuptools-scm, hatch-vcs) cannot
# build without one.
ENV = (("SETUPTOOLS_SCM_PRETEND_VERSION", "0.0.0"),)

# mutmut finds its source only through pyproject.toml / setup.cfg and cannot guess a flat layout. Point it at `src` in
# the private copy, unless the project already configures mutmut itself. Tests are never mutated.
CONFIGURE_MUTMUT = """
import sys, tomllib
from pathlib import Path
root, src = Path(sys.argv[1]), sys.argv[2]
pyproject, setup = root / "pyproject.toml", root / "setup.cfg"
tool = tomllib.loads(pyproject.read_text()).get("tool", {}) if pyproject.exists() else {}
if "mutmut" not in tool and not (setup.exists() and "[mutmut]" in setup.read_text()):
    skip = "\\n".join(f"    {pattern}" for pattern in ("*/tests/*", "*/test_*.py", "*/conftest.py"))
    with setup.open("a") as f:
        f.write(f"\\n[mutmut]\\nsource_paths = {src}\\ndo_not_mutate =\\n{skip}\\n")
""".strip()


# mutmut stops at the first test that fails under its instrumentation (a pickling or recursion-depth test, say; in its
# stats run or its clean run) and then checks no mutant. Rerun with each such test deselected, a parametrized one whole:
# fewer tests can only lower the score, never flatter it.
RUN_MUTMUT = """
import os, re, shlex, subprocess, sys
deselected = []
for _ in range(21):
    options = " ".join(shlex.quote(f"--deselect={test}") for test in deselected)
    done = subprocess.run(sys.argv[1:], env={**os.environ, "PYTEST_ADDOPTS": options}, capture_output=True, text=True)
    print(done.stdout, end="")
    seen = done.stdout + done.stderr
    new = {t for t in re.findall(r"^FAILED ([^\\s\\[]+)", seen, re.M)} - set(deselected)
    if not re.search("failed to collect stats|Failed to run clean test", seen) or not new:
        break
    deselected += sorted(new)
    print("deselected " + ", ".join(sorted(new)), file=sys.stderr)
print(done.stderr, end="", file=sys.stderr)
sys.exit(done.returncode)
""".strip()


# `mutmut results` only names the mutants. Add to each survivor the line it changed (from `mutmut show`), so the
# report says which check is missing: `<mutant>: survived<TAB><old line> -> <new line>`. The first 500, 8 at a time.
RESULTS_MUTMUT = """
import re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
def mutmut(*args):
    return subprocess.run([sys.executable, "-m", "mutmut", *args], capture_output=True, text=True)
done = mutmut("results", "--all", "true")
if done.returncode:
    print(done.stderr, end="", file=sys.stderr)
    sys.exit(done.returncode)
lines = done.stdout.splitlines()
def detail(line):
    diff = mutmut("show", line.strip().partition(": ")[0]).stdout
    sides = [re.search(f"^{mark}(?!{mark}{mark})(.*)$", diff, re.M) for mark in ("-", "[+]")]
    return f"{line}\\t{' -> '.join(' '.join(side[1].split()) for side in sides)}" if all(sides) else line
survivors = [line for line in lines if line.endswith(": survived")][:500]
with ThreadPoolExecutor(8) as pool:
    shown = dict(zip(survivors, pool.map(detail, survivors)))
print("\\n".join(shown.get(line, line) for line in lines))
""".strip()


# Cosmic Ray needs the mutable files listed (never tests, hidden or generated dirs): those of the files in scope
# (the arguments after the output directory), or all of them. Its test command runs inside each worker's own copy of
# the project, hence the relative `--project .`.
CONFIGURE_CR = """
import json, sys
from pathlib import Path
root, src, out, only = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), set(sys.argv[4:])
def mutable(path):
    parts = path.relative_to(root).parts
    skipped = any(p.startswith(".") or p in ("tests", "test", "mutants") for p in parts)
    return not skipped and not (path.name.startswith("test_") or path.name == "conftest.py")
files = sorted(str(p.relative_to(root)) for p in (root / src).rglob("*.py") if mutable(p))
files = [f for f in files if f in only] if only else files
command = "uv run --project . --with pytest pytest -x -q"
(out / "cosmic-ray.toml").write_text(
    f"[cosmic-ray]\\nmodule-path = {json.dumps(files)}\\ntest-command = {json.dumps(command)}\\n"
)
""".strip()

# Cosmic Ray's local distributor runs one mutant at a time; its http distributor runs one per worker, and a worker
# mutates the files in its own directory. So: baseline first (the tests must pass unmutated, and the timeout is five
# times how long they took), then one worker per CPU, each in a private copy, then init and exec. A worker or
# command that fails stops the run with a message; the workers are always stopped and their copies removed.
RUN_CR = """
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
project, out = Path(sys.argv[1]), Path(sys.argv[2])
base, session = (out / "cosmic-ray.toml").read_text(), out / "session.sqlite"
def cr(*args, **kwargs):
    return subprocess.run(["cosmic-ray", *args], capture_output=True, text=True, **kwargs)
def config(timeout, distributor):
    path = out / "run.toml"
    path.write_text(f"{base}timeout = {timeout}\\n\\n[cosmic-ray.distributor]\\n{distributor}\\n")
    return str(path)
def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)
start = time.monotonic()
done = cr("baseline", config(3600, 'name = "local"'))
if done.returncode:
    fail("the tests fail on the unmutated code, so mutation testing cannot start:\\n" + done.stderr[-1500:])
timeout = max(30, round(5 * (time.monotonic() - start)))
workers, copies = [], []
try:
    for _ in os.sched_getaffinity(0):
        copy = Path(tempfile.mkdtemp(prefix="cosmic-ray-worker-"))
        copies.append(copy)
        skip = shutil.ignore_patterns(".venv", ".gauntlet-out", "mutants")
        shutil.copytree(project, copy, ignore=skip, dirs_exist_ok=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        command = ["cosmic-ray", "http-worker", "--port", str(port)]
        quiet = subprocess.DEVNULL
        workers.append((subprocess.Popen(command, cwd=copy, stdout=quiet, stderr=quiet), port))
    for proc, port in workers:
        for _ in range(600):
            if proc.poll() is not None:
                fail(f"a cosmic-ray worker exited with code {proc.returncode} before it was ready")
            try:
                socket.create_connection(("127.0.0.1", port), 0.1).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            fail(f"a cosmic-ray worker did not listen on port {port} within 60 seconds")
    urls = json.dumps([f"http://127.0.0.1:{port}" for _, port in workers])
    final = config(timeout, f'name = "http"\\n\\n[cosmic-ray.distributor.http]\\nworker-urls = {urls}')
    for command in (("init", final, str(session), "--force"), ("exec", final, str(session))):
        done = cr(*command)
        if done.returncode:
            fail(f"cosmic-ray {command[0]} failed:\\n" + (done.stderr + done.stdout)[-1500:])
finally:
    for proc, _ in workers:
        proc.kill()
    for copy in copies:
        shutil.rmtree(copy, ignore_errors=True)
""".strip()

# `cosmic-ray dump` prints the whole test output and diff of every mutant; keep one short line each.
DUMP_CR = """
import json, subprocess, sys
for line in subprocess.run(sys.argv[1:], capture_output=True, text=True, check=True).stdout.splitlines():
    item, result = json.loads(line)
    mutation = item["mutations"][0]
    status = "pending" if result is None else result["test_outcome"] or result["worker_outcome"]
    print(f"{mutation['module_path']}:{mutation['start_pos'][0]} {mutation['operator_name']}: {status}")
""".strip()


def _tests(src: str, project: str, out: str) -> Step:
    uv = ("uv", "run", "--project", project)
    report = f"--cov-report=json:{out}/coverage.json"
    return Step(
        "tests",
        (*uv, "--with", PYTEST_COV, "pytest", "-q", f"--cov={src}", "--cov-branch", report),
        timeout=3600,
        env=ENV,
    )


def mutants(only: tuple[str, ...]) -> tuple[str, ...]:
    """mutmut's names for the mutants of the files in scope (`pkg.mod.x_*`, `pkg.mod.xǁ*`); none means all of them.

    mutmut names a module by its path from the project root, less a leading `src/` or `source/`. A file it cannot
    name gets no pattern: its mutants are not run, and a mutant that was not run never counts as caught."""
    found: list[str] = []
    for rel in only:
        parts = list(PurePosixPath(rel).with_suffix("").parts)
        if parts[0] in ("src", "source"):
            del parts[0]
        if parts[-1:] == ["__init__"]:
            del parts[-1]
        if parts and all(part.isidentifier() for part in parts):
            found += [f"{'.'.join(parts)}.x_*", f"{'.'.join(parts)}.xǁ*"]
    return tuple(found)


def _mutmut(src: str, project: str, out: str, only: tuple[str, ...]) -> list[Step]:
    uv = ("uv", "run", "--project", project)
    return [
        Step("mutation-config", ("python3", "-I", "-c", CONFIGURE_MUTMUT, project, src), timeout=60),
        Step(
            "mutation",
            ("python3", "-I", "-c", RUN_MUTMUT, *uv, "--with", MUTMUT, "mutmut", "run", *mutants(only)),
            timeout=7200,
            must_pass=False,
            env=ENV,
        ),
        Step(
            "mutation-results",
            (*uv, "--with", MUTMUT, "python3", "-I", "-c", RESULTS_MUTMUT),
            "mutmut-results.txt",
            env=ENV,
        ),
    ]


def _cosmic_ray(src: str, project: str, out: str, only: tuple[str, ...]) -> list[Step]:
    run = ("uv", "run", "--no-project", "--with", COSMIC_RAY, "python3", "-I", "-c")
    return [
        Step("mutation-config", ("python3", "-I", "-c", CONFIGURE_CR, project, src, out, *only), timeout=60),
        Step("mutation", (*run, RUN_CR, project, out), timeout=7200, env=ENV),
        Step(
            "mutation-results",
            (*run, DUMP_CR, "cosmic-ray", "dump", f"{out}/session.sqlite"),
            "mutmut-results.txt",
            env=ENV,
        ),
    ]


def steps(src: str, project: str, out: str, tool: str, only: tuple[str, ...]) -> list[Step]:
    return [_tests(src, project, out), *(_cosmic_ray if tool == "cosmic-ray" else _mutmut)(src, project, out, only)]
