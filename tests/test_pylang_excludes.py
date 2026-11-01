from pathlib import Path

import pytest
from helpers import tree

from gauntlet.exclusions import pragmas
from gauntlet.pylang.excludes import config_excludes
from gauntlet.scope import Scope


def test_config_excludes_from_pyproject(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {
            "pyproject.toml": '[tool.coverage.run]\nomit = ["src/legacy/*"]\n[tool.coverage.report]\nexclude_also = ["def __repr__"]\n'
            '[tool.mutmut]\ndo_not_mutate = ["src/x.py"]\n',
        },
    )
    assert config_excludes(tmp_path) == [
        "pyproject.toml: coverage omit src/legacy/*",
        "pyproject.toml: coverage exclude_also def __repr__",
        "pyproject.toml: mutmut do_not_mutate src/x.py",
    ]


def test_config_excludes_from_coveragerc(tmp_path: Path) -> None:
    tree(tmp_path, {".coveragerc": "[run]\nomit =\n    a/*\n    b/*\n"})
    assert config_excludes(tmp_path) == [".coveragerc: coverage omit a/*", ".coveragerc: coverage omit b/*"]


def test_no_config_no_excludes(tmp_path: Path) -> None:
    assert config_excludes(tmp_path) == []
    tree(tmp_path, {"pyproject.toml": "[project]\nname = 'x'\n"})
    assert config_excludes(tmp_path) == []


def test_broken_pyproject_is_an_error(tmp_path: Path) -> None:
    tree(tmp_path, {"pyproject.toml": "[tool.coverage\n"})
    with pytest.raises(ValueError, match="cannot read pyproject.toml"):
        config_excludes(tmp_path)


def test_coveragerc_without_omit_is_clean(tmp_path: Path) -> None:
    tree(tmp_path, {".coveragerc": "[run]\nbranch = True\n"})
    assert config_excludes(tmp_path) == []
    tree(tmp_path, {".coveragerc": "[report]\nshow_missing = True\n"})
    assert config_excludes(tmp_path) == []


def test_exclude_lines_are_reported_too(tmp_path: Path) -> None:
    tree(tmp_path, {"pyproject.toml": '[tool.coverage.report]\nexclude_lines = ["raise NotImplementedError"]\n'})
    assert config_excludes(tmp_path) == ["pyproject.toml: coverage exclude_lines raise NotImplementedError"]


def test_pyproject_errors_are_specific(tmp_path: Path) -> None:
    tree(tmp_path, {"pyproject.toml": "[tool.coverage\n"})
    with pytest.raises(ValueError, match=r"^cannot read pyproject\.toml$"):
        config_excludes(tmp_path)


def test_pragma_text_inside_a_python_string_is_not_a_comment(tmp_path: Path) -> None:
    tree(tmp_path, {"a.py": 'DOC = "x = 1  # pragma: no cover"\nTEXT = """\n# nosec\n"""\ny = 2  # nosec\n'})
    assert pragmas(tmp_path, "python", Scope()) == ["a.py:5: y = 2  # nosec"]


def test_python_files_that_cannot_be_tokenised_are_errors(tmp_path: Path) -> None:
    tree(tmp_path, {"bad.py": 'x = """never closed\n'})
    with pytest.raises(ValueError, match=r"^cannot analyse bad\.py: TokenError$"):
        pragmas(tmp_path, "python", Scope())


def test_setup_cfg_and_tox_ini_are_checked_too(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {
            "setup.cfg": "[coverage:run]\nomit =\n    legacy/*\n[coverage:report]\nexclude_lines = pragma: no cover\n[mutmut]\ndo_not_mutate = x.py\n",
        },
    )
    tree(tmp_path, {"tox.ini": "[coverage:report]\nexclude_also =\n    def __repr__\n"})
    assert config_excludes(tmp_path) == [
        "setup.cfg: coverage omit legacy/*",
        "setup.cfg: coverage exclude_lines pragma: no cover",
        "setup.cfg: mutmut do_not_mutate x.py",
        "tox.ini: coverage exclude_also def __repr__",
    ]


def test_coveragerc_report_settings_count(tmp_path: Path) -> None:
    tree(tmp_path, {".coveragerc": "[report]\nexclude_lines =\n    raise NotImplementedError\n"})
    assert config_excludes(tmp_path) == [".coveragerc: coverage exclude_lines raise NotImplementedError"]


def test_ini_files_without_the_sections_are_clean(tmp_path: Path) -> None:
    tree(tmp_path, {"setup.cfg": "[metadata]\nname = x\n"})
    tree(tmp_path, {"tox.ini": "[tox]\nenvlist = py\n"})
    assert config_excludes(tmp_path) == []


def test_include_and_omit_settings_that_narrow_coverage_are_exclusions(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {
            "pyproject.toml": '[tool.coverage.run]\ninclude = ["src/only/*"]\n[tool.coverage.report]\nomit = ["src/old/*"]\ninclude = ["src/new/*"]\n',
        },
    )
    tree(tmp_path, {".coveragerc": "[run]\ninclude = a/*\n[report]\nomit = b/*\ninclude = c/*\n"})
    assert config_excludes(tmp_path) == [
        "pyproject.toml: coverage run include src/only/*",
        "pyproject.toml: coverage report omit src/old/*",
        "pyproject.toml: coverage report include src/new/*",
        ".coveragerc: coverage run include a/*",
        ".coveragerc: coverage report omit b/*",
        ".coveragerc: coverage report include c/*",
    ]
