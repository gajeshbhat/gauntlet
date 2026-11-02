import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from helpers import git

from gauntlet import loop
from gauntlet.results import GateResult
from gauntlet_sandbox import ExecResult


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.py").write_text("x = 1\n")
    (root / "gauntlet.toml").write_text('language = "fake"\n')
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init", "--no-gpg-sign")
    return root


def ok(argv: Sequence[str]) -> ExecResult:  # noqa: ARG001
    return ExecResult(0, "", "")


class FakeSandbox:
    def __init__(self, behave: Callable[[Sequence[str]], ExecResult] | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, str | None], int]] = []
        self.behave: Callable[[Sequence[str]], ExecResult] = behave or ok

    def ensure(self) -> None: ...

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        self.calls.append((list(argv), dict(env or {}), timeout))
        return self.behave(argv)

    def remove(self) -> None: ...


# ---- roles
def test_role_prompts_are_minimal() -> None:
    roles = loop.load_roles()
    for text in (roles.specifier, roles.coder, roles.fixer):
        assert 0 < len(text.strip().splitlines()) <= 15


# ---- ephemeral agents
def test_each_agent_run_is_a_fresh_process_with_only_the_named_secrets() -> None:
    box = FakeSandbox()
    agent = loop.Agent(box, ("claude", "-p"), ("TOKEN",), 900)
    agent.run("ROLE", "TASK")
    agent.run("ROLE", "TASK 2")
    assert [c[0] for c in box.calls] == [["claude", "-p", "ROLE\n\nTASK"], ["claude", "-p", "ROLE\n\nTASK 2"]]
    assert all(c[1] == {"TOKEN": None} and c[2] == 900 for c in box.calls)


def test_an_unconfigured_agent_is_an_error() -> None:
    with pytest.raises(ValueError, match="agent_command"):
        loop.Agent(FakeSandbox(), (), (), 900)


# ---- workspace
def test_workspace_is_a_separate_git_repo_with_a_baseline(repo: Path, tmp_path: Path) -> None:
    ws = loop.prepare_workspace(repo, tmp_path / "ws")
    assert (ws / "a.py").read_text() == "x = 1\n"
    assert (ws / ".git").is_dir()
    assert loop.patch(ws) == ""
    (ws / "a.py").write_text("x = 2\n")
    (ws / "new.py").write_text("y = 1\n")
    text = loop.patch(ws)
    assert "-x = 1" in text and "+x = 2" in text
    assert "new.py" in text
    assert (repo / "a.py").read_text() == "x = 1\n"  # the real tree is untouched


def test_control_files_in_a_patch_are_flagged(repo: Path, tmp_path: Path) -> None:
    ws = loop.prepare_workspace(repo, tmp_path / "ws")
    (ws / "gauntlet.toml").write_text('language = "fake"\n[crap]\nmax = 99\n')
    (ws / ".workshop").mkdir()
    (ws / ".workshop" / "x.yaml").write_text("x")
    (ws / "a.py").write_text("x = 3\n")
    assert loop.control_files(loop.patch(ws)) == [".workshop/x.yaml", "gauntlet.toml"]


# ---- specify
GOOD_SPEC = "Feature: f\n  @test(t.py)\n  Scenario: s\n    When x\n    Then y\n"


def test_specify_returns_the_spec_the_agent_wrote(tmp_path: Path) -> None:
    def write(argv: Sequence[str]) -> ExecResult:
        (tmp_path / "spec.feature").write_text(GOOD_SPEC)
        return ExecResult(0, "", "")

    box = FakeSandbox(write)
    agent = loop.Agent(box, ("agent",), (), 60)
    assert loop.specify(agent, loop.load_roles(), "limit requests", tmp_path) == GOOD_SPEC
    assert "limit requests" in box.calls[0][0][-1]


def test_specify_reports_agent_failure_missing_file_and_bad_structure(tmp_path: Path) -> None:
    roles = loop.load_roles()
    with pytest.raises(ValueError, match="specifier failed"):
        loop.specify(loop.Agent(FakeSandbox(lambda a: ExecResult(1, "", "boom")), ("a",), (), 60), roles, "r", tmp_path)
    with pytest.raises(ValueError, match="did not write spec.feature"):
        loop.specify(loop.Agent(FakeSandbox(), ("a",), (), 60), roles, "r", tmp_path)

    def bad(argv: Sequence[str]) -> ExecResult:
        (tmp_path / "spec.feature").write_text("Feature: f\n  Scenario: s\n    Given a\n")
        return ExecResult(0, "", "")

    with pytest.raises(ValueError, match="'s' has no When"):
        loop.specify(loop.Agent(FakeSandbox(bad), ("a",), (), 60), roles, "r", tmp_path)


# ---- implement
def result(ok: bool, *findings: str) -> list[GateResult]:
    return [
        GateResult("clean", ok, "clean: summary", findings),
        GateResult("arch", True, "arch: fine", ("secret-ok-detail",)),
    ]


def test_passes_first_time_without_a_fixer() -> None:
    box = FakeSandbox()
    out = loop.implement(loop.Agent(box, ("a",), (), 60), loop.load_roles(), "SPEC", lambda: result(True), 3)
    assert (out.ok, out.rounds) == (True, 0)
    assert len(box.calls) == 1
    assert "SPEC" in box.calls[0][0][-1]


def test_a_fixer_sees_only_the_failures() -> None:
    box = FakeSandbox()
    outcomes = iter([result(False, "mod.py:1: f CRAP 90"), result(True)])
    out = loop.implement(loop.Agent(box, ("a",), (), 60), loop.load_roles(), "SPEC", lambda: next(outcomes), 3)
    assert (out.ok, out.rounds) == (True, 1)
    assert len(box.calls) == 2
    fixer_prompt = box.calls[1][0][-1]
    assert "mod.py:1: f CRAP 90" in fixer_prompt
    assert "clean: summary" in fixer_prompt
    assert "secret-ok-detail" not in fixer_prompt and "arch: fine" not in fixer_prompt
    assert "SPEC" not in fixer_prompt  # fresh context: no spec, no history


def test_gives_up_after_max_rounds() -> None:
    box = FakeSandbox()
    out = loop.implement(loop.Agent(box, ("a",), (), 60), loop.load_roles(), "SPEC", lambda: result(False, "f"), 2)
    assert (out.ok, out.rounds) == (False, 2)
    assert len(box.calls) == 3  # coder + two fixers
    assert out.results[0].gate == "clean"


def test_agent_failure_stops_the_loop() -> None:
    box = FakeSandbox(lambda a: ExecResult(2, "", "agent crashed"))
    with pytest.raises(ValueError, match=r"coder failed \(exit 2\): agent crashed"):
        loop.implement(loop.Agent(box, ("a",), (), 60), loop.load_roles(), "SPEC", lambda: result(True), 3)


def test_long_failure_reports_are_truncated() -> None:
    text = loop.failures(result(False, "x" * 20000), limit=500)
    assert len(text) <= 520
    assert text.endswith("[truncated]")


def test_a_failing_fixer_stops_the_loop() -> None:
    def behave(argv: Sequence[str]) -> ExecResult:
        return ExecResult(3, "", "fixer crashed") if "You are the Fixer" in argv[-1] else ExecResult(0, "", "")

    agent = loop.Agent(FakeSandbox(behave), ("a",), (), 60)
    with pytest.raises(ValueError, match=r"fixer failed \(exit 3\): fixer crashed"):
        loop.implement(agent, loop.load_roles(), "SPEC", lambda: result(False, "f"), 3)


def test_the_workspace_has_one_baseline_commit_on_main(repo: Path, tmp_path: Path) -> None:
    ws = loop.prepare_workspace(repo, tmp_path / "ws")
    log = subprocess.run(
        ["git", "-C", str(ws), "log", "--format=%s", "--all"], capture_output=True, text=True, check=True
    ).stdout.split()
    branch = subprocess.run(
        ["git", "-C", str(ws), "branch", "--show-current"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert (log, branch) == (["baseline"], "main")


def test_specify_prompt_and_messages_are_exact(tmp_path: Path) -> None:
    roles = loop.load_roles()
    box = FakeSandbox()
    with pytest.raises(ValueError, match=r"^the specifier did not write spec\.feature$"):
        loop.specify(loop.Agent(box, ("a",), (), 60), roles, "build X", tmp_path)
    assert box.calls[0][0][-1] == f"{roles.specifier}\n\nRequirement:\n\nbuild X"

    def bad(argv: Sequence[str]) -> ExecResult:
        (tmp_path / "spec.feature").write_text("Feature: f\n  Scenario: s\n    Given a\n")
        return ExecResult(0, "", "")

    with pytest.raises(ValueError, match=r"^the spec is not valid: 's' has no When; 's' has no Then; 's' has no @test"):
        loop.specify(loop.Agent(FakeSandbox(bad), ("a",), (), 60), roles, "r", tmp_path)


def test_specify_does_not_require_the_tests_to_exist_yet(tmp_path: Path) -> None:
    def write(argv: Sequence[str]) -> ExecResult:
        (tmp_path / "spec.feature").write_text(
            "Feature: f\n  @test(tests/not_yet.py::test_x)\n  Scenario: s\n    When a\n    Then b\n"
        )
        return ExecResult(0, "", "")

    assert "not_yet" in loop.specify(loop.Agent(FakeSandbox(write), ("a",), (), 60), loop.load_roles(), "r", tmp_path)


def test_control_file_matching_is_precise() -> None:
    diff = "".join(f"diff --git a/{p} b/{p}\n" for p in [
        ".github/workflows/ci.yml", "Makefile", "docs/Makefile", "gauntlet.toml.bak", "src/conftest.py",
        "conftest.py", ".workshop/x.yaml", ".workshopx/y", "pyproject.toml", "src/app.py",
    ])  # fmt: skip
    assert loop.control_files(diff) == [
        ".github/workflows/ci.yml",
        ".workshop/x.yaml",
        "Makefile",
        "conftest.py",
        "pyproject.toml",
    ]


def test_agent_failures_show_both_stderr_and_stdout() -> None:
    box = FakeSandbox(lambda argv: ExecResult(1, "Not logged in", "a warning"))
    with pytest.raises(ValueError, match=r"^coder failed \(exit 1\): a warning \| Not logged in$"):
        loop.implement(loop.Agent(box, ("a",), (), 60), loop.load_roles(), "SPEC", lambda: result(True), 3)


def test_the_patch_leaves_out_gauntlets_own_sandbox_files(repo: Path, tmp_path: Path) -> None:
    ws = loop.prepare_workspace(repo, tmp_path / "ws")
    (ws / ".workshop").mkdir()
    (ws / ".workshop" / "gauntlet-agent.yaml").write_text("name: gauntlet-agent\n")
    (ws / ".workshop.lock").write_text("lock\n")
    (ws / ".workshop" / "other.yaml").write_text("an agent added this\n")
    (ws / "a.py").write_text("x = 5\n")
    text = loop.patch(ws)
    assert "a.py" in text
    assert "gauntlet-agent.yaml" not in text and ".workshop.lock" not in text
    assert loop.control_files(text) == [".workshop/other.yaml"]  # anything else under .workshop is still flagged
