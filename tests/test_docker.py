import subprocess
from pathlib import Path

import pytest

from gauntlet.sandbox import ExecResult
from gauntlet.sandbox.docker import DockerSandbox


class FakeRunner:
    def __init__(self, *results: tuple[int, str, str], raises: BaseException | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.results = list(results) or [(0, "", "")]
        self.raises = raises

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, kwargs))
        if self.raises is not None and argv[1] == "exec":
            raise self.raises
        code, out, err = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return subprocess.CompletedProcess(argv, code, out, err)


def box(tmp_path: Path, runner: FakeRunner, **kw: str) -> DockerSandbox:
    return DockerSandbox(tmp_path, "uv:py", name="g1", user="1000:1000", run=runner, **kw)


def test_ensure_starts_a_hardened_idle_container(tmp_path: Path) -> None:
    runner = FakeRunner()
    box(tmp_path, runner).ensure()
    argv, kwargs = runner.calls[0]
    assert argv == [
        "docker", "run", "-d", "--name", "g1", "--init", "--network", "bridge", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "1024", "--user", "1000:1000", "-e", "HOME=/tmp",
        "-v", f"{tmp_path}:/project", "-w", "/project", "uv:py", "sleep", "infinity",
    ]  # fmt: skip
    assert kwargs == {"capture_output": True, "text": True, "stdin": subprocess.DEVNULL}


def test_memory_network_and_cli_are_configurable(tmp_path: Path) -> None:
    runner = FakeRunner()
    box(tmp_path, runner, cli="podman", network="none", memory="4g").ensure()
    argv = runner.calls[0][0]
    assert argv[0] == "podman"
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--memory") + 1] == "4g"


def test_no_user_flag_where_the_platform_has_no_uid(tmp_path: Path) -> None:
    runner = FakeRunner()
    DockerSandbox(tmp_path, "img", name="g1", user="", run=runner).ensure()
    assert "--user" not in runner.calls[0][0]


def test_ensure_reports_failures(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"^docker run failed: no such image$"):
        box(tmp_path, FakeRunner((1, "", "no such image"))).ensure()
    with pytest.raises(ValueError, match=r"^docker run failed: from stdout$"):
        box(tmp_path, FakeRunner((1, "from stdout", ""))).ensure()


def test_exec_runs_in_the_container_without_a_shell_and_with_a_deadline(tmp_path: Path) -> None:
    runner = FakeRunner((0, "out", "err"))
    result = box(tmp_path, runner).exec(["python3", "-c", "$(whoami)", "a b"], timeout=90)
    assert result == ExecResult(0, "out", "err")
    argv, kwargs = runner.calls[0]
    assert argv == [
        "docker", "exec", "-w", "/project", "g1", "timeout", "-k", "10", "90", "python3", "-c", "$(whoami)", "a b",
    ]  # fmt: skip
    assert kwargs == {"capture_output": True, "text": True, "stdin": subprocess.DEVNULL, "timeout": 150}


def test_env_by_value_or_by_name(tmp_path: Path) -> None:
    runner = FakeRunner()
    box(tmp_path, runner).exec(["true"], env={"GOBIN": "/project/bin", "TOKEN": None})
    argv = runner.calls[0][0]
    assert argv[argv.index("-e") : argv.index("-e") + 2] == ["-e", "GOBIN=/project/bin"]
    assert "TOKEN" in argv
    assert argv[argv.index("TOKEN") - 1] == "-e"


@pytest.mark.parametrize("name", ["bad name", "1ABC", "A=B", "", "x;y"])
def test_bad_env_names_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="bad environment variable name"):
        box(tmp_path, FakeRunner()).exec(["true"], env={name: "v"})


def test_exec_validation_matches_the_workshop_backend(tmp_path: Path) -> None:
    b = box(tmp_path, FakeRunner())
    with pytest.raises(ValueError, match=r"^empty command$"):
        b.exec([])
    with pytest.raises(ValueError, match=r"^NUL in command$"):
        b.exec(["a\0"])
    with pytest.raises(ValueError, match=r"^timeout must be between 1 and 86400 seconds$"):
        b.exec(["x"], timeout=0)


def test_a_host_side_timeout_kills_the_container_and_reports_124(tmp_path: Path) -> None:
    runner = FakeRunner(raises=subprocess.TimeoutExpired("docker", 150))
    result = box(tmp_path, runner).exec(["sleep", "999"], timeout=90)
    assert result.code == 124
    assert "timed out after 90s" in result.stderr
    assert runner.calls[-1][0] == ["docker", "rm", "-f", "g1"]


def test_remove(tmp_path: Path) -> None:
    runner = FakeRunner()
    box(tmp_path, runner).remove()
    assert runner.calls[0][0] == ["docker", "rm", "-f", "g1"]


@pytest.mark.parametrize(
    "kwargs",
    [{"cli": "rm -rf"}, {"network": "host"}, {"memory": "lots"}, {"name": "a b"}],
)
def test_unsafe_settings_are_rejected(tmp_path: Path, kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="^bad "):
        DockerSandbox(tmp_path, "img", run=FakeRunner(), **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("image", ["", "-v /:/x", "img name", "img;rm", "--privileged"])
def test_unsafe_images_are_rejected(tmp_path: Path, image: str) -> None:
    with pytest.raises(ValueError, match="^bad image"):
        DockerSandbox(tmp_path, image, run=FakeRunner())


def test_default_names_are_unique_and_valid(tmp_path: Path) -> None:
    a, b = DockerSandbox(tmp_path, "img", run=FakeRunner()), DockerSandbox(tmp_path, "img", run=FakeRunner())
    assert a.name != b.name
    assert a.name.startswith("sandbox-")
