"""Where commands run: `LocalSandbox` runs them on this machine; `gauntlet.openshell` runs them in an isolated sandbox.

Commands are argv lists: no shell ever sees them. A sandbox works on a private snapshot of the repo (`project`) and
knows where that snapshot lives from the command's point of view (`project_dir`).
"""

import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# What a command may inherit from this process, apart from UV_*: enough for uv to find its cache, tools and CA bundle.
INHERIT = (
    "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "XDG_CACHE_HOME",
)  # fmt: skip
NOT_FOUND = 127


@dataclass(frozen=True)
class ExecResult:
    code: int
    stdout: str
    stderr: str


class Sandbox(Protocol):
    project_dir: str  # where the snapshot is, as the commands see it

    def ensure(self) -> None: ...

    def exec(  # pragma: no mutate (interface stub)
        self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600
    ) -> ExecResult: ...

    def fetch(self, subdir: str) -> None:
        """Bring `subdir` of the sandbox's copy back into the snapshot ("." is all of it)."""
        ...

    def remove(self) -> None: ...


def resolve(env: Mapping[str, str | None]) -> dict[str, str]:
    """`NAME=value` as given; a bare `NAME` (None) takes its value from our environment, or is left out."""
    values = {name: os.environ.get(name) if value is None else value for name, value in env.items()}
    return {name: value for name, value in values.items() if value is not None}


class LocalSandbox:
    """Runs commands on this machine, in the snapshot, with a scrubbed environment. No isolation."""

    def __init__(self, project: Path) -> None:
        self.project, self.project_dir = project, str(project)

    def ensure(self) -> None: ...

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        inherited = {k: v for k, v in os.environ.items() if k in INHERIT or k.startswith("UV_")}
        try:
            proc = subprocess.Popen(
                list(argv), cwd=self.project, env={**inherited, **resolve(env or {})}, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", start_new_session=True,
            )  # fmt: skip
        except OSError as e:
            return ExecResult(NOT_FOUND, "", f"{argv[0]}: {e.strerror}")
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)  # the whole group: tests spawn children that would keep the pipes open
            proc.communicate()
            return ExecResult(124, "", f"timed out after {timeout}s")
        return ExecResult(proc.returncode, out, err)

    def fetch(self, subdir: str) -> None: ...  # the commands already worked in the snapshot

    def remove(self) -> None: ...
