from pathlib import Path

import pytest

from gauntlet import languages, scaffold
from gauntlet.cli import main
from gauntlet.config import load


def test_python_project_with_a_src_layout(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (tmp_path / "src").mkdir()
    path = scaffold.write_config(tmp_path)
    assert path == tmp_path / "gauntlet.toml"
    cfg = load(path)
    assert (cfg.language, cfg.src) == ("python", "src")


def test_python_project_without_src(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    cfg = load(scaffold.write_config(tmp_path))
    assert (cfg.language, cfg.src) == ("python", ".")


def test_a_requirements_file_also_means_python(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask\n")
    assert load(scaffold.write_config(tmp_path)).language == "python"


def test_go_project(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/m\n")
    cfg = load(scaffold.write_config(tmp_path))
    assert (cfg.language, cfg.packages) == ("go", ("./...",))


def test_both_languages_is_ambiguous(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module m\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    with pytest.raises(ValueError, match="found python and go; write gauntlet.toml yourself"):
        scaffold.write_config(tmp_path)
    assert not (tmp_path / "gauntlet.toml").exists()


def test_unknown_project_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot tell the language"):
        scaffold.write_config(tmp_path)


def test_an_existing_config_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module m\n")
    (tmp_path / "gauntlet.toml").write_text('language = "go"\n# mine\n')
    with pytest.raises(ValueError, match=r"gauntlet\.toml already exists"):
        scaffold.write_config(tmp_path)
    assert "# mine" in (tmp_path / "gauntlet.toml").read_text()


def test_the_generated_files_explain_the_optional_settings(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module m\n")
    assert "# mutate_only" in scaffold.write_config(tmp_path).read_text()
    other = tmp_path / "py"
    other.mkdir()
    (other / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert "# [layers]" in scaffold.write_config(other).read_text()


def test_cli_init_writes_the_file_and_says_what_next(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "go.mod").write_text("module m\n")
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


@pytest.mark.parametrize("language", [n for n in languages.NAMES if n not in ("python", "go", "cpp-clang")])
def test_init_writes_a_config_for_every_other_language(tmp_path: Path, language: str) -> None:
    (tmp_path / languages.TABLE[language].markers[0].replace("*", "app")).write_text("")
    assert load(scaffold.write_config(tmp_path)).language == language
