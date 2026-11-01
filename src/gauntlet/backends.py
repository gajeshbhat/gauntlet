"""Map the config and policy onto a sandbox: which backend, which name, image and limits."""

import shutil
from pathlib import Path

from gauntlet import languages
from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.policy import Policy
from gauntlet.sandbox import Sandbox, Which, open_sandbox, pick


def _open(kind: str, project: Path, policy: Policy, **kw: str) -> Sandbox:
    return open_sandbox(
        kind, project, cli=policy.container_cli, network=policy.docker_network, memory=policy.docker_memory, **kw
    )


def gate_sandbox(project: Path, cfg: Config, policy: Policy, which: Which = shutil.which) -> Sandbox:
    """Where `gauntlet run` executes the project's tests and mutation testing."""
    lang = languages.get(cfg.language)
    kind = pick(policy.sandbox, policy.container_cli, which)
    return _open(
        kind,
        project,
        policy,
        name="gauntlet",
        sdks=lang.sdk,
        image=policy.docker_images.get(cfg.language) or lang.image,
    )


def agent_sandbox(workspace: Path, cfg: Config, policy: Policy, which: Which = shutil.which) -> Sandbox:
    """Where the coding agent of `gauntlet loop` runs."""
    kind = pick(policy.sandbox, policy.container_cli, which)
    if kind == "docker" and not policy.docker_image_agent:
        raise GauntletError("docker_image_agent is not set in the policy; build one from examples/agent.Dockerfile")
    sdks = f"{languages.get(cfg.language).sdk},claude-code"
    return _open(kind, workspace, policy, name="gauntlet-agent", sdks=sdks, image=policy.docker_image_agent)
