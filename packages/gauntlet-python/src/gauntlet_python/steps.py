"""The fixed, pinned commands that produce the Python artifacts in the sandbox."""

from gauntlet.plugin import Step

PYTEST_COV = "pytest-cov==7.1.0"
MUTMUT = "mutmut==3.8.1"


def steps(src: str, project: str, out: str) -> list[Step]:
    uv = ("uv", "run", "--project", project)
    report = f"--cov-report=json:{out}/coverage.json"
    return [
        Step(
            "tests", (*uv, "--with", PYTEST_COV, "pytest", "-q", f"--cov={src}", "--cov-branch", report), timeout=3600
        ),
        Step("mutation", (*uv, "--with", MUTMUT, "mutmut", "run"), timeout=7200, must_pass=False),
        Step("mutation-results", (*uv, "--with", MUTMUT, "mutmut", "results", "--all", "true"), "mutmut-results.txt"),
    ]
