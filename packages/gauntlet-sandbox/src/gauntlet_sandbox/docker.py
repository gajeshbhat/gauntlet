"""Run commands in a Docker (or Podman) container: a sandbox for macOS, Windows and Linux.

The container is hardened (no capabilities, no new privileges, a PID limit, the caller's uid) and only sees a throwaway
copy of the project. Docker Desktop and Colima run containers inside a VM, which is the isolation boundary on macOS and
Windows. Commands are argv lists: no shell ever sees them.
"""

import os
import re
import secrets
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from gauntlet_sandbox.api import PROJECT_DIR, ExecResult, Runner, env_entries, validate_exec
from gauntlet_sandbox.errors import SandboxError
from gauntlet_sandbox.names import IMAGE, MEMORY

CLI = re.compile(r"^[a-z][a-z0-9-]*$")
NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,62}$")
NETWORKS = ("bridge", "none")
GRACE = 10  # seconds `timeout` waits after TERM before KILL
BACKSTOP = 60  # extra seconds before we give up on the docker CLI itself


def _default_user() -> str:
    return f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else ""  # no uid on Windows: Docker Desktop maps it


class DockerSandbox:
    def __init__(
        self,
        project: Path,
        image: str,
        *,
        cli: str = "docker",
        network: str = "bridge",
        memory: str = "",
        name: str | None = None,
        prefix: str = "sandbox",
        user: str | None = None,
        run: Runner = subprocess.run,
    ) -> None:
        name = name if name is not None else f"{prefix}-{secrets.token_hex(4)}"
        for kind, value, ok in (
            ("image", image, IMAGE.match(image)),
            ("cli", cli, CLI.match(cli)),
            ("network", network, network in NETWORKS),
            ("memory", memory, memory == "" or MEMORY.match(memory)),
            ("name", name, NAME.match(name)),
        ):
            if not ok:
                raise SandboxError(f"bad {kind} {value!r}")
        self.project, self.image, self.cli, self.network, self.memory = project, image, cli, network, memory
        self.name, self.user, self._run = name, _default_user() if user is None else user, run

    def _docker(self, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
        extra = {} if timeout is None else {"timeout": timeout}
        return self._run([self.cli, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, **extra)

    def ensure(self) -> None:
        flags = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "1024"]
        flags += ["--memory", self.memory] if self.memory else []
        flags += ["--user", self.user] if self.user else []
        done = self._docker(
            "run", "-d", "--name", self.name, "--init", "--network", self.network, *flags,
            "-e", "HOME=/tmp", "-v", f"{self.project}:{PROJECT_DIR}", "-w", PROJECT_DIR,
            self.image, "sleep", "infinity",
        )  # fmt: skip
        if done.returncode != 0:
            raise SandboxError(f"{self.cli} run failed: {done.stderr.strip() or done.stdout.strip()}")

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        validate_exec(argv, timeout)
        flags = [arg for entry in env_entries(env or {}) for arg in ("-e", entry)]
        command = ["timeout", "-k", str(GRACE), str(timeout), *argv]
        try:
            done = self._docker("exec", "-w", PROJECT_DIR, *flags, self.name, *command, timeout=timeout + BACKSTOP)
        except subprocess.TimeoutExpired:
            self.remove()  # the docker CLI hung: kill the whole container
            return ExecResult(124, "", f"timed out after {timeout}s")
        return ExecResult(done.returncode, done.stdout, done.stderr)

    def remove(self) -> None:
        self._docker("rm", "-f", self.name)
