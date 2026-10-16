import subprocess
from pathlib import Path

import pytest

from gauntlet.sandbox import ExecResult, WorkshopSandbox


class FakeRunner:
    def __init__(self, *results: tuple[int, str, str]) -> None:
        self.calls: list[list[str]] = []
        self.results = list(results) or [(0, "", "")]

    def __call__(self, argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        code, out, err = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return subprocess.CompletedProcess(argv, code, out, err)


def sandbox(tmp_path: Path, runner: FakeRunner, sdks: str = "uv") -> WorkshopSandbox:
    return WorkshopSandbox(tmp_path, name="gauntlet", sdks=sdks, run=runner)


def test_exec_builds_an_argv_without_a_shell(tmp_path: Path) -> None:
    runner = FakeRunner((0, "out", "err"))
    result = sandbox(tmp_path, runner).exec(["python3", "-c", "print(1)", "$(whoami)", "a b"], timeout=90)
    assert result == ExecResult(0, "out", "err")
    assert runner.calls == [
        [
            "workshop",
            "-p",
            str(tmp_path),
            "exec",
            "--timeout",
            "90s",
            "gauntlet",
            "--",
            "python3",
            "-c",
            "print(1)",
            "$(whoami)",
            "a b",
        ]
    ]


def test_exec_passes_env_by_value_or_by_name(tmp_path: Path) -> None:
    runner = FakeRunner()
    sandbox(tmp_path, runner).exec(["true"], env={"GOBIN": "/project/bin", "TOKEN": None})
    call = runner.calls[0]
    assert call[call.index("--env") : call.index("--env") + 2] == ["--env", "GOBIN=/project/bin"]
    assert "TOKEN" in call
    assert call[call.index("TOKEN") - 1] == "--env"
    assert not any("secret" in a for a in call)


@pytest.mark.parametrize("name", ["bad name", "1ABC", "A=B", "", "x;y"])
def test_exec_rejects_bad_env_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="bad environment variable name"):
        sandbox(tmp_path, FakeRunner()).exec(["true"], env={name: "v"})


def test_exec_rejects_nul_and_empty_commands(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty command"):
        sandbox(tmp_path, FakeRunner()).exec([])
    with pytest.raises(ValueError, match="NUL"):
        sandbox(tmp_path, FakeRunner()).exec(["a\0b"])


def test_exec_rejects_unreasonable_timeouts(tmp_path: Path) -> None:
    for bad in (0, -1, 86401):
        with pytest.raises(ValueError, match="timeout"):
            sandbox(tmp_path, FakeRunner()).exec(["true"], timeout=bad)


def test_names_are_validated(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bad workshop name"):
        WorkshopSandbox(tmp_path, name="a b")
    with pytest.raises(ValueError, match="bad sdk list"):
        WorkshopSandbox(tmp_path, sdks="go,rm -rf")


def test_ensure_creates_the_definition_then_launches(tmp_path: Path) -> None:
    runner = FakeRunner()
    sandbox(tmp_path, runner, sdks="go,uv").ensure()
    assert runner.calls == [
        ["workshop", "-p", str(tmp_path), "init", "gauntlet", "--sdks", "go,uv"],
        ["workshop", "-p", str(tmp_path), "launch", "gauntlet"],
    ]


def test_ensure_keeps_an_existing_definition_it_has_not_written_itself(tmp_path: Path) -> None:
    (tmp_path / ".workshop").mkdir()
    (tmp_path / ".workshop" / "gauntlet.yaml").write_text("name: gauntlet\n")
    with pytest.raises(ValueError, match="already has a workshop definition"):
        sandbox(tmp_path, FakeRunner()).ensure()


def test_ensure_reports_failures(tmp_path: Path) -> None:
    runner = FakeRunner((0, "", ""), (1, "", "no network"))
    with pytest.raises(ValueError, match="workshop launch failed: no network"):
        sandbox(tmp_path, runner).ensure()
    runner = FakeRunner((1, "", "bad sdk"))
    with pytest.raises(ValueError, match="workshop init failed: bad sdk"):
        sandbox(tmp_path, runner).ensure()


def test_remove(tmp_path: Path) -> None:
    runner = FakeRunner()
    sandbox(tmp_path, runner).remove()
    assert runner.calls == [["workshop", "-p", str(tmp_path), "remove", "gauntlet"]]


class KwargsRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.kwargs: list[dict[str, object]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.kwargs.append(kwargs)
        return super().__call__(argv, **kwargs)


def test_every_workshop_call_captures_text_output(tmp_path: Path) -> None:
    runner = KwargsRunner()
    box = sandbox(tmp_path, runner)
    box.ensure()
    box.exec(["true"])
    box.remove()
    assert runner.kwargs == [{"capture_output": True, "text": True}] * 4


def test_default_timeout_and_inclusive_limits(tmp_path: Path) -> None:
    runner = FakeRunner()
    box = sandbox(tmp_path, runner)
    box.exec(["true"])
    box.exec(["true"], timeout=1)
    box.exec(["true"], timeout=86_400)
    assert [c[c.index("--timeout") + 1] for c in runner.calls] == ["600s", "1s", "86400s"]


def test_error_messages_are_exact(tmp_path: Path) -> None:
    box = sandbox(tmp_path, FakeRunner())
    with pytest.raises(ValueError, match=r"^bad environment variable name 'bad name'$"):
        box.exec(["x"], env={"bad name": "v"})
    with pytest.raises(ValueError, match=r"^empty command$"):
        box.exec([])
    with pytest.raises(ValueError, match=r"^NUL in command$"):
        box.exec(["a\0"])
    with pytest.raises(ValueError, match=r"^timeout must be between 1 and 86400 seconds$"):
        box.exec(["x"], timeout=0)
    with pytest.raises(ValueError, match=r"^bad workshop name 'a b'$"):
        WorkshopSandbox(tmp_path, name="a b")
    with pytest.raises(ValueError, match=r"^bad sdk list 'x y'$"):
        WorkshopSandbox(tmp_path, sdks="x y")


def test_names_with_the_allowed_shapes_are_accepted(tmp_path: Path) -> None:
    WorkshopSandbox(tmp_path, name="a", sdks="go")
    WorkshopSandbox(tmp_path, name="gauntlet-agent-2", sdks="go,uv,claude-code")
    WorkshopSandbox(tmp_path, name="x" * 31)
    with pytest.raises(ValueError, match="bad workshop name"):
        WorkshopSandbox(tmp_path, name="x" * 32)


def test_ensure_error_prefers_stderr_and_falls_back_to_stdout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"^workshop init failed: from stdout$"):
        sandbox(tmp_path, FakeRunner((1, "from stdout", ""))).ensure()
    with pytest.raises(ValueError, match=r"^workshop init failed: from stderr$"):
        sandbox(tmp_path, FakeRunner((1, "ignored", "from stderr"))).ensure()


def test_existing_definition_message(tmp_path: Path) -> None:
    (tmp_path / ".workshop").mkdir()
    (tmp_path / ".workshop" / "gauntlet.yaml").write_text("x")
    with pytest.raises(ValueError, match=rf"^{tmp_path} already has a workshop definition for 'gauntlet'$"):
        sandbox(tmp_path, FakeRunner()).ensure()
