from pathlib import Path

from gauntlet import scaffold
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


def test_a_flat_layout_points_src_at_the_one_package(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    for name in ("mypkg", "tests", "docs"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "__init__.py").write_text("")
    assert load(scaffold.write_config(tmp_path)).src == "mypkg"


def test_several_top_level_packages_keep_src_at_the_root(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "__init__.py").write_text("")
    assert load(scaffold.write_config(tmp_path)).src == "."
