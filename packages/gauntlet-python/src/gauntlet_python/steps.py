"""The fixed, pinned commands that produce the Python artifacts inside the sandbox."""

from gauntlet.plugin import Step
from gauntlet_sandbox import PROJECT_DIR

UV = ("uv", "run", "--project", PROJECT_DIR)
PYTEST_COV = "pytest-cov==7.1.0"
MUTMUT = "mutmut==3.8.0"


def steps(src: str, out: str) -> list[Step]:
    report = f"--cov-report=json:{out}/coverage.json"
    return [
        Step(
            "tests", (*UV, "--with", PYTEST_COV, "pytest", "-q", f"--cov={src}", "--cov-branch", report), timeout=3600
        ),
        Step("mutation", (*UV, "--with", MUTMUT, "mutmut", "run"), timeout=7200, must_pass=False),
        Step("mutation-results", (*UV, "--with", MUTMUT, "mutmut", "results", "--all", "true"), "mutmut-results.txt"),
    ]
