from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet import backends, languages
from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.sandbox.docker import DockerSandbox
from gauntlet.sandbox.workshop import WorkshopSandbox


def which(*present: str) -> Callable[[str], str | None]:
    return lambda cmd: f"/usr/bin/{cmd}" if cmd in present else None


def test_gate_sandbox_on_workshop(tmp_path: Path) -> None:
    box = backends.gate_sandbox(tmp_path, Config("fake"), Policy(sandbox="workshop"), which("workshop"))
    assert isinstance(box, WorkshopSandbox)
    assert (box.name, box.sdks) == ("gauntlet", "fake-sdk")


def test_gate_sandbox_on_docker_uses_the_language_image_and_policy_settings(tmp_path: Path) -> None:
    pol = Policy(sandbox="docker", docker_network="none", docker_memory="2g", docker_images={"fake": "py:9"})
    box = backends.gate_sandbox(tmp_path, Config("fake"), pol, which("docker"))
    assert isinstance(box, DockerSandbox)
    assert (box.image, box.network, box.memory, box.cli) == ("py:9", "none", "2g", "docker")
    assert box.name.startswith("gauntlet-")
    py = backends.gate_sandbox(tmp_path, Config("fake"), Policy(sandbox="docker"), which("docker"))
    assert isinstance(py, DockerSandbox)
    assert py.image == languages.get("fake").image


def test_the_container_cli_comes_from_the_policy(tmp_path: Path) -> None:
    box = backends.gate_sandbox(tmp_path, Config("fake"), Policy(container_cli="podman"), which("podman"))
    assert isinstance(box, DockerSandbox)
    assert box.cli == "podman"


def test_agent_sandbox_on_workshop_adds_claude_code(tmp_path: Path) -> None:
    box = backends.agent_sandbox(tmp_path, Config("fake"), Policy(sandbox="workshop"), which("workshop"))
    assert isinstance(box, WorkshopSandbox)
    assert (box.name, box.sdks) == ("gauntlet-agent", "fake-sdk,claude-code")


def test_agent_sandbox_on_docker_needs_an_agent_image(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="docker_image_agent is not set.*examples/agent.Dockerfile"):
        backends.agent_sandbox(tmp_path, Config("fake"), Policy(sandbox="docker"), which("docker"))
    box = backends.agent_sandbox(
        tmp_path, Config("fake"), Policy(sandbox="docker", docker_image_agent="my/agent"), which("docker")
    )
    assert isinstance(box, DockerSandbox)
    assert box.image == "my/agent"
    assert box.name.startswith("gauntlet-agent-")
