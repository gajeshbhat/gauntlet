import json
from pathlib import Path

import pytest
from helpers import (
    Out,
    committed_py_project,
    sandbox_factory,
)

from gauntlet import cli
from gauntlet.cli import main


# ---- run (sandboxed pipeline)
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
