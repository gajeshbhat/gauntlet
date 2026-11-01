"""Builders shared by the tests: file trees, small projects, git, and a stand-in for the gate sandbox."""

import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.sandbox import ExecResult
from gauntlet.sandbox.workshop import WorkshopSandbox

BRANCHY = "def g(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(1, 8)) + "    return 0\n"


Out = pytest.CaptureFixture[str]


def project(root: Path, toml: str) -> Path:
    (root / "gauntlet.toml").write_text(toml)
    return root


def py_project(root: Path, toml: str = 'language = "fake"\n', covered: bool = False) -> Path:
    project(root, toml)
    (root / "mod.py").write_text(BRANCHY)
    missing = [] if covered else list(range(2, 17))
    executed = list(range(1, 17)) if covered else [1]
    cov = {"files": {"mod.py": {"executed_lines": executed, "missing_lines": missing}}}
    (root / "coverage.json").write_text(json.dumps(cov))
    return root


def tree(root: Path, files: Mapping[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


class RunSandbox:
    """Stands in for Workshop: 'runs' the python steps by writing what they would have produced."""

    def __init__(self, project: Path, covered: bool = True) -> None:
        self.project, self.covered, self.removed = project, covered, False

    def ensure(self) -> None: ...

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        out = self.project / ".gauntlet-out"
        if "fake-test" in argv:
            cov = {"files": {"mod.py": {"executed_lines": list(range(1, 17)), "missing_lines": []}}}
            if not self.covered:
                cov = {"files": {"mod.py": {"executed_lines": [1], "missing_lines": list(range(2, 17))}}}
            (out / "coverage.json").write_text(json.dumps(cov))
        if "fake-results" in argv:
            return ExecResult(0, "p.x: killed\n" * 9 + "p.y: survived\n", "")
        return ExecResult(0, "", "")

    def remove(self) -> None:
        self.removed = True


def sandbox_factory(covered: bool = True) -> Callable[[Path, Config, Policy], RunSandbox]:
    return lambda project, cfg, policy: RunSandbox(project, covered)  # noqa: ARG005


def committed_py_project(root: Path, toml: str = 'language = "fake"\n') -> Path:
    project(root, toml)
    (root / "mod.py").write_text(BRANCHY)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    return root


def failing_workshop(name: str) -> Callable[[Path, Config, Policy], WorkshopSandbox]:
    """A real Workshop sandbox whose `workshop` binary always fails with 'boom'."""

    def boom(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, "", "boom")

    return lambda project, cfg, policy: WorkshopSandbox(project, name, run=boom)  # noqa: ARG005
