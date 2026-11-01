"""What every sandbox backend offers. Commands are argv lists: no shell ever sees them."""

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from gauntlet_sandbox.errors import SandboxError
from gauntlet_sandbox.names import ENV_NAME

PROJECT_DIR = "/project"  # where the project is mounted inside the sandbox
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
            raise SandboxError(f"bad environment variable name {name!r}")
        entries.append(name if value is None else f"{name}={value}")
    return entries


def validate_exec(argv: Sequence[str], timeout: int) -> None:
    if not argv:
        raise SandboxError("empty command")
    if any("\0" in a for a in argv):
        raise SandboxError("NUL in command")
    if not 0 < timeout <= MAX_TIMEOUT:
        raise SandboxError(f"timeout must be between 1 and {MAX_TIMEOUT} seconds")
