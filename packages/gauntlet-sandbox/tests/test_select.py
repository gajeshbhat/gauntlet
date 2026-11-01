from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet_sandbox import SandboxError, open_sandbox, pick
from gauntlet_sandbox.docker import DockerSandbox
from gauntlet_sandbox.workshop import WorkshopSandbox


def which(*present: str) -> Callable[[str], str | None]:
    return lambda cmd: f"/usr/bin/{cmd}" if cmd in present else None


def test_a_sandbox_error_is_a_value_error() -> None:
    assert issubclass(SandboxError, ValueError)


@pytest.mark.parametrize(
    ("present", "expected"),
    [(("workshop", "docker"), "workshop"), (("workshop",), "workshop"), (("docker",), "docker")],
)
def test_auto_prefers_workshop_then_docker(present: tuple[str, ...], expected: str) -> None:
    assert pick("auto", "docker", which(*present)) == expected


def test_auto_with_nothing_installed_explains_the_options() -> None:
    with pytest.raises(SandboxError, match="no sandbox found: install Canonical Workshop .*or Docker"):
        pick("auto", "docker", which())


def test_auto_uses_the_given_container_cli() -> None:
    assert pick("auto", "podman", which("podman")) == "docker"
    with pytest.raises(SandboxError, match="no sandbox found"):
        pick("auto", "podman", which("docker"))


def test_an_explicit_choice_must_be_installed() -> None:
    assert pick("docker", "docker", which("docker")) == "docker"
    with pytest.raises(SandboxError, match=r"^sandbox = \"workshop\" but `workshop` is not installed$"):
        pick("workshop", "docker", which("docker"))
    with pytest.raises(SandboxError, match=r"^sandbox = \"docker\" but `docker` is not installed$"):
        pick("docker", "docker", which("workshop"))


def test_open_a_workshop(tmp_path: Path) -> None:
    box = open_sandbox("workshop", tmp_path, name="w1", sdks="go,uv")
    assert isinstance(box, WorkshopSandbox)
    assert (box.name, box.sdks, box.project) == ("w1", "go,uv", tmp_path)


def test_open_a_docker_container_named_after_the_caller(tmp_path: Path) -> None:
    box = open_sandbox("docker", tmp_path, name="proj", image="img", cli="podman", network="none", memory="1g")
    assert isinstance(box, DockerSandbox)
    assert (box.image, box.cli, box.network, box.memory) == ("img", "podman", "none", "1g")
    assert box.name.startswith("proj-")


def test_an_unknown_kind_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match=r"^unknown sandbox 'lxc'$"):
        open_sandbox("lxc", tmp_path, name="x")
