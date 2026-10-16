"""Run commands inside a Canonical Workshop sandbox. Commands are argv lists: no shell ever sees them."""

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
SDKS = re.compile(r"^[a-z][a-z0-9-]*(,[a-z][a-z0-9-]*)*$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_TIMEOUT = 86_400

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class ExecResult:
    code: int
    stdout: str
    stderr: str


class Sandbox(Protocol):
    def ensure(self) -> None: ...

    def exec(  # pragma: no mutate (interface stub)
        self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600
    ) -> ExecResult: ...

    def remove(self) -> None: ...


def _env_args(env: Mapping[str, str | None]) -> list[str]:
    args: list[str] = []
    for name, value in env.items():
        if not ENV_NAME.match(name):
            raise ValueError(f"bad environment variable name {name!r}")
        args += ["--env", name if value is None else f"{name}={value}"]  # name only: value inherited, never in argv
    return args


class WorkshopSandbox:
    def __init__(self, project: Path, name: str = "gauntlet", sdks: str = "uv", run: Runner = subprocess.run) -> None:
        if not NAME.match(name):
            raise ValueError(f"bad workshop name {name!r}")
        if not SDKS.match(sdks):
            raise ValueError(f"bad sdk list {sdks!r}")
        self.project, self.name, self.sdks, self._run = project, name, sdks, run

    def _workshop(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run(["workshop", "-p", str(self.project), *args], capture_output=True, text=True)

    def ensure(self) -> None:
        if (self.project / ".workshop" / f"{self.name}.yaml").exists():
            raise ValueError(f"{self.project} already has a workshop definition for {self.name!r}")
        for step in (("init", self.name, "--sdks", self.sdks), ("launch", self.name)):
            done = self._workshop(*step)
            if done.returncode != 0:
                raise ValueError(f"workshop {step[0]} failed: {done.stderr.strip() or done.stdout.strip()}")

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if not argv:
            raise ValueError("empty command")
        if any("\0" in a for a in argv):
            raise ValueError("NUL in command")
        if not 0 < timeout <= MAX_TIMEOUT:
            raise ValueError(f"timeout must be between 1 and {MAX_TIMEOUT} seconds")
        done = self._workshop("exec", "--timeout", f"{timeout}s", *_env_args(env or {}), self.name, "--", *argv)
        return ExecResult(done.returncode, done.stdout, done.stderr)

    def remove(self) -> None:
        self._workshop("remove", self.name)
