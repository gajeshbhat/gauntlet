from pathlib import Path

import pytest

from gauntlet import scaffold
from gauntlet.cli import main
from gauntlet.config import load


def test_a_project_with_a_src_layout(tmp_path: Path) -> None:
    (tmp_path / "fake.marker").write_text("x\n")
    (tmp_path / "src").mkdir()
    path = scaffold.write_config(tmp_path)
    assert path == tmp_path / "gauntlet.toml"
    cfg = load(path)
    assert (cfg.language, cfg.src) == ("fake", "src")


def test_unknown_project_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot tell the language"):
        scaffold.write_config(tmp_path)


def test_an_existing_config_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / "fake.marker").write_text("x\n")
    (tmp_path / "gauntlet.toml").write_text('language = "fake"\n# mine\n')
    with pytest.raises(ValueError, match=r"gauntlet\.toml already exists"):
        scaffold.write_config(tmp_path)
    assert "# mine" in (tmp_path / "gauntlet.toml").read_text()


def test_the_generated_files_explain_the_optional_settings(tmp_path: Path) -> None:
    (tmp_path / "fake.marker").write_text("x\n")
    assert "# [layers]" in scaffold.write_config(tmp_path).read_text()


def test_cli_init_writes_the_file_and_says_what_next(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "fake.marker").write_text("x\n")
    assert main(["init", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"wrote {tmp_path / 'gauntlet.toml'}" in out
    assert "gauntlet run" in out


def test_cli_init_refuses_cleanly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init", str(tmp_path)]) == 2
    assert "cannot tell the language" in capsys.readouterr().err


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    from importlib.metadata import version

    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out == f"gauntlet {version('gauntlet')}\n"
