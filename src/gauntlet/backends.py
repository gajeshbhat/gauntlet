"""Pick the sandbox backend from the policy: Canonical Workshop (Linux) or Docker/Podman (Linux, macOS, Windows)."""

import shutil
from collections.abc import Callable
from pathlib import Path

from gauntlet import languages
from gauntlet.config import Config
from gauntlet.docker import DockerSandbox
from gauntlet.policy import Policy
from gauntlet.sandbox import Sandbox, WorkshopSandbox

Which = Callable[[str], str | None]
NO_SANDBOX = (
    "no sandbox found: install Canonical Workshop (Linux: sudo snap install workshop --classic) "
    "or Docker (Linux, macOS, Windows)"
)


def _installed(policy: Policy, which: Which) -> dict[str, bool]:
    return {"workshop": which("workshop") is not None, "docker": which(policy.container_cli) is not None}


def pick(policy: Policy, which: Which = shutil.which) -> str:
    installed = _installed(policy, which)
    if policy.sandbox == "auto":
        for name in ("workshop", "docker"):
            if installed[name]:
                return name
        raise ValueError(NO_SANDBOX)
    if not installed[policy.sandbox]:
        tool = "workshop" if policy.sandbox == "workshop" else policy.container_cli
        raise ValueError(f'sandbox = "{policy.sandbox}" but `{tool}` is not installed')
    return policy.sandbox


def _docker(project: Path, image: str, policy: Policy) -> DockerSandbox:
    return DockerSandbox(
        project, image, cli=policy.container_cli, network=policy.docker_network, memory=policy.docker_memory
    )


def gate_sandbox(project: Path, cfg: Config, policy: Policy, which: Which = shutil.which) -> Sandbox:
    """Where `gauntlet run` executes the project's tests and mutation testing."""
    if pick(policy, which) == "workshop":
        return WorkshopSandbox(project, sdks=languages.get(cfg.language).sdk)
    return _docker(project, policy.docker_images.get(cfg.language) or languages.get(cfg.language).image, policy)


def agent_sandbox(workspace: Path, cfg: Config, policy: Policy, which: Which = shutil.which) -> Sandbox:
    """Where the coding agent of `gauntlet loop` runs."""
    if pick(policy, which) == "workshop":
        return WorkshopSandbox(workspace, name="gauntlet-agent", sdks=f"{languages.get(cfg.language).sdk},claude-code")
    if not policy.docker_image_agent:
        raise ValueError("docker_image_agent is not set in the policy; build one from examples/agent.Dockerfile")
    return _docker(workspace, policy.docker_image_agent, policy)
