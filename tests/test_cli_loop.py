import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from cli_helpers import (
    BRANCHY,
    Out,
    RunSandbox,
    committed_py_project,
)

from gauntlet import cli
from gauntlet.cli import main
from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.sandbox import ExecResult

# ---- loop
AGENT_POLICY = 'allow_unstamped = true\nagent_command = ["agent", "-p"]\nagent_env = ["TOKEN"]\nmax_rounds = 2\n'
LOOP_SPEC = "Feature: f\n  @test(test_mod.py::test_g)\n  Scenario: s\n    When x\n    Then y\n"


class AgentBox:
    """Stands in for the agent sandbox: acts on the workspace like a (very small) coding agent would."""

    def __init__(self, project: Path, script: Callable[[str, Path], ExecResult]) -> None:
        self.project, self.script, self.prompts = project, script, []

    prompts: list[str]

    def ensure(self) -> None: ...

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        self.prompts.append(argv[-1])
        return self.script(argv[-1], self.project)

    def remove(self) -> None: ...


class LoopGates(RunSandbox):
    """Gate sandbox whose coverage depends on whether the workspace got the 'fix'."""

    def __init__(self, project: Path) -> None:
        super().__init__(project, covered=(project / "fixed.txt").exists())


def agent_script(prompt: str, project: Path) -> ExecResult:
    if "You are the Specifier" in prompt:
        (project / "spec.feature").write_text(LOOP_SPEC)
    elif "You are the Coder" in prompt:
        (project / "test_mod.py").write_text("def test_g():\n    assert True\n")
        (project / "mod.py").write_text(BRANCHY)
    elif "You are the Fixer" in prompt:
        (project / "fixed.txt").write_text("fixed")
    return ExecResult(0, "", "")


def loop_gates(project: Path, cfg: Config, policy: Policy) -> LoopGates:  # noqa: ARG001
    return LoopGates(project)


def loop_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_policy: Callable[[str], Path],
    script: Callable[[str, Path], ExecResult] = agent_script,
    policy_text: str = AGENT_POLICY,
) -> tuple[Path, Path, list[AgentBox]]:
    root = committed_py_project(tmp_path / "repo") if (tmp_path / "repo").mkdir() is None else tmp_path
    boxes: list[AgentBox] = []

    def make_agent(workspace: Path, cfg: Config, policy: Policy) -> AgentBox:
        boxes.append(AgentBox(workspace, script))
        return boxes[-1]

    monkeypatch.setattr(cli, "MAKE_AGENT_SANDBOX", make_agent)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", loop_gates)
    return root, write_policy(policy_text), boxes


def test_loop_needs_an_agent_in_the_policy(tmp_path: Path, capsys: Out, write_policy: Callable[[str], Path]) -> None:
    root = committed_py_project(tmp_path)
    pol = write_policy("allow_unstamped = true\n")
    assert main(["loop", str(root), "--requirement", "x", "--policy", str(pol)]) == 2
    assert "no agent configured" in capsys.readouterr().err


def test_loop_needs_a_requirement_or_a_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy)
    assert main(["loop", str(root), "--policy", str(pol)]) == 2
    assert "--requirement" in capsys.readouterr().err


def test_loop_without_an_approved_spec_stops_after_the_specifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, boxes = loop_setup(tmp_path, monkeypatch, write_policy)
    assert main(["loop", str(root), "--requirement", "limit things", "--policy", str(pol)]) == 3
    out = root / ".gauntlet-loop"
    assert (out / "spec.feature").read_text() == LOOP_SPEC
    assert "rerun with --spec" in capsys.readouterr().out
    assert len(boxes[0].prompts) == 1 and "limit things" in boxes[0].prompts[0]
    assert not (root / "spec.feature").exists()  # the real tree is untouched


def test_loop_with_an_approved_spec_implements_and_hands_back_a_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, boxes = loop_setup(tmp_path, monkeypatch, write_policy)
    spec_file = tmp_path / "approved.feature"
    spec_file.write_text(LOOP_SPEC)
    # first evaluation fails (no 'fixed.txt'), the fixer adds it, the second passes
    code = main(["loop", str(root), "--spec", str(spec_file), "--policy", str(pol)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert [("Coder" in p, "Fixer" in p) for p in boxes[0].prompts] == [(True, False), (False, True)]
    loop_dir = root / ".gauntlet-loop"
    patch_text = (loop_dir / "loop.patch").read_text()
    assert "test_mod.py" in patch_text and "fixed.txt" in patch_text
    assert (loop_dir / "EVIDENCE.md").read_text().startswith("# Evidence report")
    assert not (root / "test_mod.py").exists()  # nothing landed in the real tree
    assert "fixer rounds: 1" in out


def test_loop_reports_failure_and_flags_control_file_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    def sneaky(prompt: str, project: Path) -> ExecResult:
        if "You are the Coder" in prompt:
            (project / "test_mod.py").write_text("def test_g(): pass\n")
            (project / "mod.py").write_text(BRANCHY)
            (project / "gauntlet.toml").write_text('language = "python"\n[crap]\nmax = 99\n')
        return ExecResult(0, "", "")  # the fixer never fixes anything

    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy, sneaky)
    spec_file = tmp_path / "approved.feature"
    spec_file.write_text(LOOP_SPEC)
    assert main(["loop", str(root), "--spec", str(spec_file), "--policy", str(pol)]) == 1
    out = capsys.readouterr().out
    assert "fixer rounds: 2" in out
    assert "touches control files: gauntlet.toml" in out
    assert "over CRAP 8" in out  # the agent's own gauntlet.toml edit did not relax the limit


def test_loop_agent_failure_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy, lambda p, d: ExecResult(7, "", "agent crashed"))
    assert main(["loop", str(root), "--requirement", "x", "--policy", str(pol)]) == 2
    assert capsys.readouterr().err == "gauntlet: specifier failed (exit 7): agent crashed\n"


def test_loop_prints_exact_summary_and_writes_a_complete_evidence_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    import hashlib

    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy)
    spec_file = tmp_path / "approved.feature"
    spec_file.write_text(LOOP_SPEC)
    assert main(["loop", str(root), "--spec", str(spec_file), "--policy", str(pol)]) == 0
    out = capsys.readouterr().out.splitlines()
    loop_dir = root / ".gauntlet-loop"
    assert out[-1] == f"fixer rounds: 1; patch: {loop_dir / 'loop.patch'}; evidence: {loop_dir / 'EVIDENCE.md'}"
    text = (loop_dir / "EVIDENCE.md").read_text()
    assert "- Language: python" in text
    assert f"`{hashlib.sha256((root / 'gauntlet.toml').read_bytes()).hexdigest()}`" in text
    assert re.search(r"Source fingerprint: `[0-9a-f]{64}`", text)
    assert re.search(r"Generated \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00 by gauntlet", text)
    assert f"gauntlet loop {root} --spec {spec_file}" in text
    assert (loop_dir / "artifacts" / "gauntlet-manifest.json").exists()
