"""The fixed, pinned commands that produce the Python artifacts inside the sandbox."""

from gauntlet.plugin import Step
from gauntlet_sandbox import PROJECT_DIR

UV = ("uv", "run", "--project", PROJECT_DIR)
PYTEST_COV = "pytest-cov==7.1.0"
MUTMUT = "mutmut==3.8.1"
# The sandbox copy has no git history, so projects that read their version from git (setuptools-scm, hatch-vcs) cannot
# build without one.
ENV = (("SETUPTOOLS_SCM_PRETEND_VERSION", "0.0.0"),)

# mutmut finds its source only through pyproject.toml / setup.cfg and cannot guess a flat layout. Point it at `src` in
# the sandbox's private copy, unless the project already configures mutmut itself. Tests are never mutated.
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


def steps(src: str, out: str) -> list[Step]:
    report = f"--cov-report=json:{out}/coverage.json"
    return [
        Step(
            "tests",
            (*UV, "--with", PYTEST_COV, "pytest", "-q", f"--cov={src}", "--cov-branch", report),
            timeout=3600,
            env=ENV,
        ),
        Step("mutation-config", ("python3", "-c", CONFIGURE_MUTMUT, PROJECT_DIR, src), timeout=60),
        Step(
            "mutation",
            ("python3", "-c", RUN_MUTMUT, *UV, "--with", MUTMUT, "mutmut", "run"),
            timeout=7200,
            must_pass=False,
            env=ENV,
        ),
        Step(
            "mutation-results",
            (*UV, "--with", MUTMUT, "mutmut", "results", "--all", "true"),
            "mutmut-results.txt",
            env=ENV,
        ),
    ]
