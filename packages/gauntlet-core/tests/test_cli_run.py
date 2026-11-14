import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from helpers import (
    Out,
    RunSandbox,
    broken_sandbox,
    committed_py_project,
    sandbox_factory,
)

from gauntlet import cli
from gauntlet.cli import main
from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.sandbox import ExecResult


# ---- run (the pipeline in a sandbox)
def test_run_produces_artifacts_in_the_sandbox_then_evaluates_every_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["run", str(root)]) == 0
    out = capsys.readouterr().out
    assert "produced coverage.json, mutmut-results.txt" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "exclusions:" in out
    assert "mutation score 90.0% >= 90%" in out
    assert (root / ".gauntlet" / "gauntlet-manifest.json").exists()


def test_run_fails_when_a_gate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory(covered=False))
    assert main(["run", str(root)]) == 1


def test_run_honours_out_and_ignores_stale_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path / "repo") if (tmp_path / "repo").mkdir() is None else tmp_path
    (root / "coverage.json").write_text('{"files": {}}')  # stale junk next to the sources must not matter
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    out = tmp_path / "elsewhere"
    assert main(["run", str(root), "--out", str(out)]) == 0
    assert (out / "coverage.json").exists()
    capsys.readouterr()


def test_gates_default_to_the_results_of_the_last_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["run", str(root)]) == 0
    capsys.readouterr()
    assert main(["clean", str(root)]) == 0  # finds .gauntlet/ by itself: stamped, so it verifies
    (root / "mod.py").write_text("def g():\n    return 2\n")
    assert main(["clean", str(root)]) == 2
    assert "stale" in capsys.readouterr().err


def test_stamp_never_blesses_the_results_of_an_old_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory(covered=False))
    assert main(["run", str(root)]) == 1  # leaves .gauntlet/ with uncovered results
    capsys.readouterr()
    covered = {"mod.py": {"executed_lines": list(range(1, 17)), "missing_lines": []}}
    (root / "coverage.json").write_text(json.dumps({"files": covered}))  # fresh artifacts next to the sources
    assert main(["stamp", str(root)]) == 0
    assert "stamped coverage.json" in capsys.readouterr().out
    assert (root / "gauntlet-manifest.json").exists()
    assert main(["clean", str(root), "--artifacts", str(root)]) == 0  # the fresh ones, not the old run's


# ---- where project code runs
def test_run_says_once_that_project_code_runs_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["run", str(root)]) == 0
    err = capsys.readouterr().err
    assert err.count("project code runs on this machine") == 1
    assert 'sandbox = "openshell"' in err and "--sandbox openshell" in err


def test_the_flag_picks_the_sandbox_for_this_run_and_silences_the_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    seen: list[str] = []

    def factory(project: Path, cfg: Config, policy: Policy) -> RunSandbox:
        seen.append(policy.sandbox)
        return RunSandbox(project)

    monkeypatch.setattr(cli, "MAKE_SANDBOX", factory)
    assert main(["run", str(root), "--sandbox", "openshell"]) == 0
    assert seen == ["openshell"]
    assert "project code runs" not in capsys.readouterr().err


def test_pin_does_not_write_the_sandbox_flag_into_the_policy(tmp_path: Path, capsys: Out) -> None:
    root = committed_py_project(tmp_path)
    pol = tmp_path / "policy.toml"
    assert main(["pin", str(root), "--policy", str(pol), "--sandbox", "openshell"]) == 0
    assert 'sandbox = "local"' in pol.read_text()


def test_run_with_a_sandbox_that_cannot_start_is_a_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", broken_sandbox)
    assert main(["run", str(root), "--sandbox", "openshell"]) == 2
    assert capsys.readouterr().err == "gauntlet: cannot start an OpenShell sandbox: boom\n"


# ---- only what changed
def changed_project(root: Path) -> Path:
    """mod.py (fully covered by the stand-in sandbox) plus a change to it since the commit."""
    committed_py_project(root)
    (root / "mod.py").write_text((root / "mod.py").read_text() + "\n\ndef h():\n    return 1\n")
    return root


def test_changed_limits_the_run_to_the_lines_that_differ_from_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = changed_project(tmp_path)
    seen: list[list[str]] = []

    class Spy(RunSandbox):
        def exec(
            self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600
        ) -> ExecResult:
            seen.append(list(argv))
            return super().exec(argv, env, timeout)

    def factory(project: Path, cfg: Config, policy: Policy) -> RunSandbox:  # noqa: ARG001
        return Spy(project)

    monkeypatch.setattr(cli, "MAKE_SANDBOX", factory)
    report = tmp_path.parent / f"{tmp_path.name}-evidence.md"
    assert main(["run", str(root), "--changed", "--report", str(report)]) == 1  # h is new and nothing covers it
    assert ["fake-mutate", "mutmut", "mod.py"] in seen
    out = capsys.readouterr().out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out  # h alone, not g
    assert "stray: survived" not in out
    text = report.read_text()
    assert "- Scope: mod.py:17-20\n" in text
    assert f"gauntlet run {root} --changed HEAD\n" in text


def test_changed_takes_the_commit_to_compare_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out) -> None:
    root = changed_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["clean", str(root), "--changed=HEAD~0", "--artifacts", str(tmp_path / "none")]) == 2
    assert "is not stamped" in capsys.readouterr().err  # the ref was fine: it got as far as the artifacts
    assert main(["clean", str(root), "--changed", "nope"]) == 2
    assert "--changed: 'nope' is not a commit" in capsys.readouterr().err


def test_changed_with_nothing_changed_is_refused(tmp_path: Path, capsys: Out) -> None:
    root = committed_py_project(tmp_path)
    assert main(["run", str(root), "--changed"]) == 2
    assert capsys.readouterr().err == "gauntlet: nothing to check: no source file differs from HEAD\n"


def test_only_and_changed_add_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out) -> None:
    root = changed_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    report = tmp_path.parent / f"{tmp_path.name}-evidence.md"
    main(["run", str(root), "--only", "mod.py:1-1", "--only", "x.py", "--changed", "HEAD", "--report", str(report)])
    assert "clean: 2 function(s) checked" in capsys.readouterr().out
    text = report.read_text()
    assert "- Scope: mod.py:1-1, x.py, mod.py:17-20\n" in text
    assert f"gauntlet run {root} --only mod.py:1-1 --only x.py --changed HEAD\n" in text


def test_a_report_of_an_unscoped_run_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    report = tmp_path.parent / f"{tmp_path.name}-evidence.md"
    assert main(["run", str(root), "--report", str(report)]) == 0
    text = report.read_text()
    assert "- Scope: all source\n" in text
    assert f"```\ngauntlet run {root}\n```" in text
    capsys.readouterr()
