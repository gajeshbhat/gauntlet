"""Pick the sandbox backend: Canonical Workshop (Linux) or Docker/Podman (Linux, macOS, Windows)."""

import shutil
from collections.abc import Callable
from pathlib import Path

from gauntlet_sandbox.api import Sandbox
from gauntlet_sandbox.docker import DockerSandbox
from gauntlet_sandbox.errors import SandboxError
from gauntlet_sandbox.workshop import WorkshopSandbox

Which = Callable[[str], str | None]
NO_SANDBOX = (
    "no sandbox found: install Canonical Workshop (Linux: sudo snap install workshop --classic) "
    "or Docker (Linux, macOS, Windows)"
)


def pick(preference: str, cli: str = "docker", which: Which = shutil.which) -> str:
    """ "workshop" or "docker": `preference` if it is installed, else (for "auto") the first one that is."""
    tools = {"workshop": "workshop", "docker": cli}
    installed = [name for name, tool in tools.items() if which(tool)]
    if preference == "auto":
        if not installed:
            raise SandboxError(NO_SANDBOX)
        return installed[0]
    if preference not in installed:
        raise SandboxError(f'sandbox = "{preference}" but `{tools[preference]}` is not installed')
    return preference


def open_sandbox(
    kind: str,
    project: Path,
    *,
    name: str,
    sdks: str = "uv",
    image: str = "",
    cli: str = "docker",
    network: str = "bridge",
    memory: str = "",
) -> Sandbox:
    """A `kind` ("workshop" or "docker") sandbox over `project`; `name` names the workshop or prefixes the container."""
    if kind == "workshop":
        return WorkshopSandbox(project, name, sdks)
    if kind == "docker":
        return DockerSandbox(project, image, cli=cli, network=network, memory=memory, prefix=name)
    raise SandboxError(f"unknown sandbox {kind!r}")
