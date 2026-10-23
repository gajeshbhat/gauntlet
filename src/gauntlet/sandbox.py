"""Run commands inside a Canonical Workshop sandbox. Commands are argv lists: no shell ever sees them."""

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gauntlet.errors import GauntletError
from gauntlet.names import ENV_NAME

NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
SDKS = re.compile(r"^[a-z][a-z0-9-]*(,[a-z][a-z0-9-]*)*$")
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


def env_entries(env: Mapping[str, str | None]) -> list[str]:
    """`NAME=value` entries, or a bare `NAME` (value inherited from our environment, so never in an argv)."""
    entries: list[str] = []
    for name, value in env.items():
        if not ENV_NAME.match(name):
            raise GauntletError(f"bad environment variable name {name!r}")
        entries.append(name if value is None else f"{name}={value}")
    return entries


def validate_exec(argv: Sequence[str], timeout: int) -> None:
    if not argv:
        raise GauntletError("empty command")
    if any("\0" in a for a in argv):
        raise GauntletError("NUL in command")
    if not 0 < timeout <= MAX_TIMEOUT:
        raise GauntletError(f"timeout must be between 1 and {MAX_TIMEOUT} seconds")


class WorkshopSandbox:
    def __init__(self, project: Path, name: str = "gauntlet", sdks: str = "uv", run: Runner = subprocess.run) -> None:
        if not NAME.match(name):
            raise GauntletError(f"bad workshop name {name!r}")
        if not SDKS.match(sdks):
            raise GauntletError(f"bad sdk list {sdks!r}")
        self.project, self.name, self.sdks, self._run = project, name, sdks, run

    def _workshop(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run(
            ["workshop", "-p", str(self.project), *args], capture_output=True, text=True, stdin=subprocess.DEVNULL
        )  # a closed stdin: an inherited one makes tools such as `claude -p` wait for input

    def ensure(self) -> None:
        if (self.project / ".workshop" / f"{self.name}.yaml").exists():
            raise GauntletError(f"{self.project} already has a workshop definition for {self.name!r}")
        for step in (("init", self.name, "--sdks", self.sdks), ("launch", self.name)):
            done = self._workshop(*step)
            if done.returncode != 0:
                raise GauntletError(f"workshop {step[0]} failed: {done.stderr.strip() or done.stdout.strip()}")

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        validate_exec(argv, timeout)
        flags = [arg for entry in env_entries(env or {}) for arg in ("--env", entry)]
        done = self._workshop("exec", "--timeout", f"{timeout}s", *flags, self.name, "--", *argv)
        return ExecResult(done.returncode, done.stdout, done.stderr)

    def remove(self) -> None:
        self._workshop("remove", self.name)
