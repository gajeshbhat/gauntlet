import json
from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet.cli import main

BRANCHY = "def g(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(1, 9)) + "    return 0\n"


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


def test_clean_passes_when_functions_are_covered(tmp_path: Path) -> None:
    project(tmp_path, 'language = "python"\n')
    (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
    cov = {"files": {"mod.py": {"executed_lines": [1, 2], "missing_lines": []}}}
    (tmp_path / "coverage.json").write_text(json.dumps(cov))
    assert main(["clean", str(tmp_path)]) == 0


def test_root_defaults_to_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project(tmp_path, 'language = "python"\n')
    monkeypatch.chdir(tmp_path)
    assert main(["arch"]) == 0


def test_usage_names_the_program(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert capsys.readouterr().out.startswith("usage: gauntlet")


def fake_harden(result: tuple[float, list[str]], seen: list[Path]) -> Callable[[Path], tuple[float, list[str]]]:
    def check(root: Path) -> tuple[float, list[str]]:
        seen.append(root)
        return result

    return check


def test_harden_fails_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project(tmp_path, 'language = "python"\n[mutation]\nmin_score = 90\n')
    seen: list[Path] = []
    survivors = (50.0, ["p.x_a__mutmut_2: survived"])
    monkeypatch.setattr("gauntlet.cli.harden.check", fake_harden(survivors, seen))
    assert main(["harden", str(tmp_path)]) == 1
    assert seen == [tmp_path]
    out = capsys.readouterr().out
    assert "p.x_a__mutmut_2: survived" in out
    assert "mutation score 50.0% < 90%" in out


def test_harden_passes_at_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project(tmp_path, 'language = "python"\n[mutation]\nmin_score = 90\n')
    monkeypatch.setattr("gauntlet.cli.harden.check", fake_harden((90.0, []), []))
    assert main(["harden", str(tmp_path)]) == 0
    assert "mutation score 90.0% >= 90%" in capsys.readouterr().out


GOCYCLO = "18 device DiskMount lxd/device/disk.go:28:1\n6 device Small lxd/device/disk.go:95:1\n"
COVER = (
    "example.com/m/lxd/device/disk.go:28:\t\tDiskMount\t\t0.0%\n"
    "example.com/m/lxd/device/disk.go:95:\t\tSmall\t\t100.0%\n"
)


def go_project(root: Path) -> Path:
    project(root, 'language = "go"\n[layers]\norder = ["m/web", "m/domain"]\n')
    (root / "gocyclo.txt").write_text(GOCYCLO)
    (root / "cover-func.txt").write_text(COVER)
    (root / "imports.txt").write_text("m/domain m/web\n")
    return root


def test_go_clean_fails_on_risky_function(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["clean", str(go_project(tmp_path))]) == 1
    assert "lxd/device/disk.go:28: DiskMount CRAP 342.0 > 8" in capsys.readouterr().out


def test_go_clean_scope_can_exclude_the_offender(tmp_path: Path) -> None:
    assert main(["clean", str(go_project(tmp_path)), "--only", "lxd/device/disk.go:90-99"]) == 0


def test_python_clean_respects_scope(tmp_path: Path) -> None:
    project(tmp_path, 'language = "python"\n')
    (tmp_path / "mod.py").write_text(BRANCHY)
    cov = {"files": {"mod.py": {"executed_lines": [1], "missing_lines": list(range(2, 19))}}}
    (tmp_path / "coverage.json").write_text(json.dumps(cov))
    assert main(["clean", str(tmp_path), "--only", "other.py"]) == 0
    assert main(["clean", str(tmp_path), "--only", "mod.py:1-1"]) == 1
    assert main(["clean", str(tmp_path), "--only", "mod.py:5-9"]) == 0


def test_go_arch_reports_package_without_a_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["arch", str(go_project(tmp_path))]) == 1
    assert capsys.readouterr().out.strip() == "m/domain: m/domain imports outer layer m/web"


def test_go_harden_reads_gremlins_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = go_project(tmp_path)
    muts = [{"type": "X", "status": "LIVED", "line": 3, "column": 1}]
    (root / "mutation.json").write_text(json.dumps({"files": [{"file_name": "a.go", "mutations": muts}]}))
    assert main(["harden", str(root)]) == 1
    assert "a.go:3:1 X LIVED" in capsys.readouterr().out


def test_go_missing_artifact_says_how_to_make_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project(tmp_path, 'language = "go"\n')
    assert main(["clean", str(tmp_path)]) == 2
    assert capsys.readouterr().err.strip().endswith("produce it with: gocyclo ./...")


def test_bad_scope_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["arch", str(go_project(tmp_path)), "--only", "x.go:9-1"]) == 2
    assert "scope" in capsys.readouterr().err


def test_artifacts_can_live_elsewhere(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root, art = tmp_path / "pilot", tmp_path / "art"
    art.mkdir()
    root.mkdir()
    go_project(root)
    for name in ("gocyclo.txt", "cover-func.txt", "imports.txt"):
        (art / name).write_text((root / name).read_text())
        (root / name).unlink()
    assert main(["clean", str(root), "--artifacts", str(art)]) == 1
    assert "DiskMount CRAP" in capsys.readouterr().out
