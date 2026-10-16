import json
from pathlib import Path

import pytest

from gauntlet.cli import main

BRANCHY = (
    "def g(x):\n"
    + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(1, 9))
    + "    return 0\n"
)


def project(root: Path, toml: str) -> Path:
    (root / "gauntlet.toml").write_text(toml)
    return root


def test_unknown_gate_exits_with_usage_error() -> None:
    with pytest.raises(SystemExit) as e:
        main(["bogus"])
    assert e.value.code == 2


def test_missing_config_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["arch", str(tmp_path)]) == 2
    assert "gauntlet.toml" in capsys.readouterr().err


def test_go_not_implemented_yet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project(tmp_path, 'language = "go"\n')
    assert main(["clean", str(tmp_path)]) == 2
    assert "go" in capsys.readouterr().err


def test_arch_fails_on_outward_import(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "web").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "web" / "v.py").write_text("")
    (tmp_path / "domain" / "m.py").write_text("from web import v\n")
    assert main(["arch", str(tmp_path)]) == 1
    assert "domain/m.py:1: domain imports outer layer web" in capsys.readouterr().out


def test_arch_passes_clean_tree(tmp_path: Path) -> None:
    project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    assert main(["arch", str(tmp_path)]) == 0


def test_clean_fails_on_risky_function(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project(tmp_path, 'language = "python"\n')
    (tmp_path / "mod.py").write_text(BRANCHY)
    cov = {"files": {"mod.py": {"executed_lines": [1], "missing_lines": list(range(2, 19))}}}
    (tmp_path / "coverage.json").write_text(json.dumps(cov))
    assert main(["clean", str(tmp_path)]) == 1
    assert "mod.py:1: g CRAP" in capsys.readouterr().out


def test_clean_without_coverage_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project(tmp_path, 'language = "python"\n')
    assert main(["clean", str(tmp_path)]) == 2
    assert "--cov-report=json" in capsys.readouterr().err


def test_check_runs_both_gates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "web").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "m.py").write_text("import web\n")
    (tmp_path / "coverage.json").write_text(json.dumps({"files": {}}))
    assert main(["check", str(tmp_path)]) == 1
    assert "imports outer layer" in capsys.readouterr().out
