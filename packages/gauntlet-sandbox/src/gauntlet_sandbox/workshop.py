"""Canonical Workshop (LXD) sandbox: a named workshop defined in the project's `.workshop/` directory."""

import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from gauntlet_sandbox.api import ExecResult, Runner, env_entries, validate_exec
from gauntlet_sandbox.errors import SandboxError

NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
SDKS = re.compile(r"^[a-z][a-z0-9-]*(,[a-z][a-z0-9-]*)*$")


class WorkshopSandbox:
    def __init__(self, project: Path, name: str, sdks: str = "uv", run: Runner = subprocess.run) -> None:
        if not NAME.match(name):
            raise SandboxError(f"bad workshop name {name!r}")
        if not SDKS.match(sdks):
            raise SandboxError(f"bad sdk list {sdks!r}")
        self.project, self.name, self.sdks, self._run = project, name, sdks, run

    def _workshop(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run(
            ["workshop", "-p", str(self.project), *args], capture_output=True, text=True, stdin=subprocess.DEVNULL
        )  # a closed stdin: an inherited one makes tools such as `claude -p` wait for input

    def ensure(self) -> None:
        if (self.project / ".workshop" / f"{self.name}.yaml").exists():
            raise SandboxError(f"{self.project} already has a workshop definition for {self.name!r}")
        for step in (("init", self.name, "--sdks", self.sdks), ("launch", self.name)):
            done = self._workshop(*step)
            if done.returncode != 0:
                raise SandboxError(f"workshop {step[0]} failed: {done.stderr.strip() or done.stdout.strip()}")

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        validate_exec(argv, timeout)
        flags = [arg for entry in env_entries(env or {}) for arg in ("--env", entry)]
        done = self._workshop("exec", "--timeout", f"{timeout}s", *flags, self.name, "--", *argv)
        return ExecResult(done.returncode, done.stdout, done.stderr)

    def remove(self) -> None:
        self._workshop("remove", self.name)
