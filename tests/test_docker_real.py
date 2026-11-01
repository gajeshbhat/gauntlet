"""Runs real containers. Opt in with GAUNTLET_DOCKER_TESTS=1 (needs Docker and network to pull the image)."""

import os
from pathlib import Path

import pytest

from gauntlet import languages
from gauntlet.docker import DockerSandbox

pytestmark = pytest.mark.skipif(os.environ.get("GAUNTLET_DOCKER_TESTS") != "1", reason="set GAUNTLET_DOCKER_TESTS=1")


@pytest.fixture
def box(tmp_path: Path):  # type: ignore[no-untyped-def]  # noqa: ANN201
    sandbox = DockerSandbox(tmp_path, languages.TABLE["python"].image, memory="512m")
    sandbox.ensure()
    yield sandbox
    sandbox.remove()


def test_container_is_hardened_and_sees_only_the_project(box: DockerSandbox, tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("hi")
    probe = (
        "grep CapEff /proc/self/status; grep NoNewPrivs /proc/self/status; cat /sys/fs/cgroup/memory.max; ls /project"
    )
    out = box.exec(["sh", "-c", probe]).stdout
    assert "CapEff:\t0000000000000000" in out
    assert "NoNewPrivs:\t1" in out
    assert "536870912" in out
    assert "marker.txt" in out


def test_a_runaway_command_is_stopped(box: DockerSandbox) -> None:
    assert box.exec(["sleep", "30"], timeout=2).code == 124


def test_host_environment_does_not_leak_and_named_secrets_do_not_appear_in_argv(
    box: DockerSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GAUNTLET_TEST_SECRET", "s3cret")
    assert box.exec(["sh", "-c", "echo [${GAUNTLET_TEST_SECRET}]"]).stdout.strip() == "[]"
    assert (
        box.exec(["sh", "-c", "echo [${GAUNTLET_TEST_SECRET}]"], env={"GAUNTLET_TEST_SECRET": None}).stdout.strip()
        == "[s3cret]"
    )
