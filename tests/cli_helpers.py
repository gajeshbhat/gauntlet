"""Builders shared by the CLI tests: small projects, git, and a stand-in for the gate sandbox."""

import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.sandbox import ExecResult

BRANCHY = "def g(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(1, 8)) + "    return 0\n"


def _go_branches(name: str, count: int) -> list[str]:
    body = [line for i in range(count) for line in (f"\tif x == {i} {{", f"\t\treturn {i}", "\t}")]
    return [f"func {name}(x int) int {{", *body, "\treturn 0", "}"]


GO_SOURCE = "\n".join(
    ["package device", *[""] * 26, *_go_branches("DiskMount", 17), *[""] * 13, *_go_branches("Small", 5)]
)
GO_COVER = (
    "mode: set\nexample.com/m/lxd/device/disk.go:28.1,81.2 1 0\nexample.com/m/lxd/device/disk.go:95.1,112.2 1 1\n"
)
Out = pytest.CaptureFixture[str]


def project(root: Path, toml: str) -> Path:
    (root / "gauntlet.toml").write_text(toml)
    return root


def py_project(root: Path, toml: str = 'language = "python"\n', covered: bool = False) -> Path:
    project(root, toml)
    (root / "mod.py").write_text(BRANCHY)
    missing = [] if covered else list(range(2, 17))
    executed = list(range(1, 17)) if covered else [1]
    cov = {"files": {"mod.py": {"executed_lines": executed, "missing_lines": missing}}}
    (root / "coverage.json").write_text(json.dumps(cov))
    return root


def go_project(root: Path, extra: str = "") -> Path:
    project(root, 'language = "go"\n[layers]\norder = ["m/web", "m/domain"]\n' + extra)
    (root / "lxd" / "device").mkdir(parents=True)
    (root / "lxd" / "device" / "disk.go").write_text(GO_SOURCE + "\n")
    (root / "cover.out").write_text(GO_COVER)
    (root / "imports.txt").write_text("m/domain m/web\n")
    return root


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
        if "pytest" in argv:
            cov = {"files": {"mod.py": {"executed_lines": list(range(1, 17)), "missing_lines": []}}}
            if not self.covered:
                cov = {"files": {"mod.py": {"executed_lines": [1], "missing_lines": list(range(2, 17))}}}
            (out / "coverage.json").write_text(json.dumps(cov))
        if list(argv[-3:]) == ["results", "--all", "true"]:
            return ExecResult(0, "p.x: killed\n" * 9 + "p.y: survived\n", "")
        return ExecResult(0, "", "")

    def remove(self) -> None:
        self.removed = True


def sandbox_factory(covered: bool = True) -> Callable[[Path, Config, Policy], RunSandbox]:
    return lambda project, cfg, policy: RunSandbox(project, covered)  # noqa: ARG005


def committed_py_project(root: Path, toml: str = 'language = "python"\n') -> Path:
    project(root, toml)
    (root / "mod.py").write_text(BRANCHY)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    return root
