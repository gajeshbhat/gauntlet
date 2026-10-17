from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet import backends
from gauntlet.config import Config
from gauntlet.docker import DockerSandbox
from gauntlet.policy import Policy
from gauntlet.sandbox import WorkshopSandbox


def which(*present: str) -> Callable[[str], str | None]:
    return lambda cmd: f"/usr/bin/{cmd}" if cmd in present else None


@pytest.mark.parametrize(
    ("present", "expected"),
    [(("workshop", "docker"), "workshop"), (("workshop",), "workshop"), (("docker",), "docker")],
)
def test_auto_prefers_workshop_then_docker(present: tuple[str, ...], expected: str) -> None:
    assert backends.pick(Policy(), which(*present)) == expected


def test_auto_with_nothing_installed_explains_the_options() -> None:
    with pytest.raises(ValueError, match="no sandbox found: install Canonical Workshop .*or Docker"):
        backends.pick(Policy(), which())


def test_auto_uses_the_configured_container_cli() -> None:
    assert backends.pick(Policy(container_cli="podman"), which("podman")) == "docker"
    with pytest.raises(ValueError, match="no sandbox found"):
        backends.pick(Policy(container_cli="podman"), which("docker"))


def test_an_explicit_choice_must_be_installed() -> None:
    assert backends.pick(Policy(sandbox="docker"), which("docker")) == "docker"
    with pytest.raises(ValueError, match=r"^sandbox = \"workshop\" but `workshop` is not installed$"):
        backends.pick(Policy(sandbox="workshop"), which("docker"))
    with pytest.raises(ValueError, match=r"^sandbox = \"docker\" but `docker` is not installed$"):
        backends.pick(Policy(sandbox="docker"), which("workshop"))


def test_gate_sandbox_on_workshop(tmp_path: Path) -> None:
    box = backends.gate_sandbox(tmp_path, Config("go"), Policy(sandbox="workshop"), which("workshop"))
    assert isinstance(box, WorkshopSandbox)
    assert (box.name, box.sdks) == ("gauntlet", "go")
    py = backends.gate_sandbox(tmp_path, Config("python"), Policy(sandbox="workshop"), which("workshop"))
    assert isinstance(py, WorkshopSandbox)
    assert py.sdks == "uv"


def test_gate_sandbox_on_docker_uses_the_language_image_and_policy_settings(tmp_path: Path) -> None:
    pol = Policy(sandbox="docker", docker_network="none", docker_memory="2g", docker_image_go="golang:9")
    box = backends.gate_sandbox(tmp_path, Config("go"), pol, which("docker"))
    assert isinstance(box, DockerSandbox)
    assert (box.image, box.network, box.memory, box.cli) == ("golang:9", "none", "2g", "docker")
    py = backends.gate_sandbox(tmp_path, Config("python"), Policy(sandbox="docker"), which("docker"))
    assert isinstance(py, DockerSandbox)
    assert py.image == Policy().docker_image_python


def test_agent_sandbox_on_workshop_adds_claude_code(tmp_path: Path) -> None:
    box = backends.agent_sandbox(tmp_path, Config("go"), Policy(sandbox="workshop"), which("workshop"))
    assert isinstance(box, WorkshopSandbox)
    assert (box.name, box.sdks) == ("gauntlet-agent", "go,claude-code")


def test_agent_sandbox_on_docker_needs_an_agent_image(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="docker_image_agent is not set.*examples/agent.Dockerfile"):
        backends.agent_sandbox(tmp_path, Config("python"), Policy(sandbox="docker"), which("docker"))
    box = backends.agent_sandbox(
        tmp_path, Config("python"), Policy(sandbox="docker", docker_image_agent="my/agent"), which("docker")
    )
    assert isinstance(box, DockerSandbox)
    assert box.image == "my/agent"
