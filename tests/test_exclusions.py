from pathlib import Path

import pytest

from gauntlet.exclusions import config_excludes, pragmas
from gauntlet.scope import Scope, parse


def put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_counts_every_kind_of_exclusion_comment(tmp_path: Path) -> None:
    put(tmp_path, "a.py", "x = 1  # pragma: no mutate\ny = 2  # pragma: no cover\nz = 3  # nosec\nw = 4\n")
    put(tmp_path, "b.go", "package b\nfunc f() {} //nolint:gocyclo\n// ordinary comment\n")
    assert pragmas(tmp_path, "python", Scope()) == [
        "a.py:1: x = 1  # pragma: no mutate",
        "a.py:2: y = 2  # pragma: no cover",
        "a.py:3: z = 3  # nosec",
    ]
    assert pragmas(tmp_path, "go", Scope()) == ["b.go:2: func f() {} //nolint:gocyclo"]


def test_only_files_of_the_language_and_not_vendored_dirs(tmp_path: Path) -> None:
    put(tmp_path, ".venv/lib/x.py", "# pragma: no cover\n")
    put(tmp_path, "node_modules/m.py", "# pragma: no cover\n")
    put(tmp_path, "notes.txt", "# pragma: no cover\n")
    put(tmp_path, "src/real.py", "y = 1  # pragma: no cover\n")
    assert pragmas(tmp_path, "python", Scope()) == ["src/real.py:1: y = 1  # pragma: no cover"]


def test_scope_limits_the_files_and_lines_counted(tmp_path: Path) -> None:
    put(tmp_path, "a.py", "# nosec\n\n# nosec\n")
    assert len(pragmas(tmp_path, "python", parse(["a.py:3-3"]))) == 1
    assert pragmas(tmp_path, "python", parse(["b.py"])) == []


def test_symlinks_out_of_the_root_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.py").write_text("# nosec\n")
    (root / "link.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(ValueError, match="escapes the project root"):
        pragmas(root, "python", Scope())


def test_config_excludes_from_pyproject(tmp_path: Path) -> None:
    put(
        tmp_path,
        "pyproject.toml",
        '[tool.coverage.run]\nomit = ["src/legacy/*"]\n[tool.coverage.report]\nexclude_also = ["def __repr__"]\n'
        '[tool.mutmut]\ndo_not_mutate = ["src/x.py"]\n',
    )
    assert config_excludes(tmp_path) == [
        "pyproject.toml: coverage omit src/legacy/*",
        "pyproject.toml: coverage exclude_also def __repr__",
        "pyproject.toml: mutmut do_not_mutate src/x.py",
    ]


def test_config_excludes_from_coveragerc(tmp_path: Path) -> None:
    put(tmp_path, ".coveragerc", "[run]\nomit =\n    a/*\n    b/*\n")
    assert config_excludes(tmp_path) == [".coveragerc: coverage omit a/*", ".coveragerc: coverage omit b/*"]


def test_no_config_no_excludes(tmp_path: Path) -> None:
    assert config_excludes(tmp_path) == []
    put(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")
    assert config_excludes(tmp_path) == []


def test_broken_pyproject_is_an_error(tmp_path: Path) -> None:
    put(tmp_path, "pyproject.toml", "[tool.coverage\n")
    with pytest.raises(ValueError, match="cannot read pyproject.toml"):
        config_excludes(tmp_path)


def test_coveragerc_without_omit_is_clean(tmp_path: Path) -> None:
    put(tmp_path, ".coveragerc", "[run]\nbranch = True\n")
    assert config_excludes(tmp_path) == []
    put(tmp_path, ".coveragerc", "[report]\nshow_missing = True\n")
    assert config_excludes(tmp_path) == []


def test_exclude_lines_are_reported_too(tmp_path: Path) -> None:
    put(tmp_path, "pyproject.toml", '[tool.coverage.report]\nexclude_lines = ["raise NotImplementedError"]\n')
    assert config_excludes(tmp_path) == ["pyproject.toml: coverage exclude_lines raise NotImplementedError"]


def test_pyproject_errors_are_specific(tmp_path: Path) -> None:
    put(tmp_path, "pyproject.toml", "[tool.coverage\n")
    with pytest.raises(ValueError, match=r"^cannot read pyproject\.toml$"):
        config_excludes(tmp_path)


def test_pragma_text_inside_a_python_string_is_not_a_comment(tmp_path: Path) -> None:
    put(tmp_path, "a.py", 'DOC = "x = 1  # pragma: no cover"\nTEXT = """\n# nosec\n"""\ny = 2  # nosec\n')
    assert pragmas(tmp_path, "python", Scope()) == ["a.py:5: y = 2  # nosec"]


def test_python_files_that_cannot_be_tokenised_are_errors(tmp_path: Path) -> None:
    put(tmp_path, "bad.py", 'x = """never closed\n')
    with pytest.raises(ValueError, match=r"^cannot analyse bad\.py$"):
        pragmas(tmp_path, "python", Scope())


def test_go_comments_are_still_found_by_pattern(tmp_path: Path) -> None:
    put(tmp_path, "m.go", "package m\n\nfunc F() {} // nolint\n")
    assert pragmas(tmp_path, "go", Scope()) == ["m.go:3: func F() {} // nolint"]


def test_setup_cfg_and_tox_ini_are_checked_too(tmp_path: Path) -> None:
    put(
        tmp_path,
        "setup.cfg",
        "[coverage:run]\nomit =\n    legacy/*\n[coverage:report]\nexclude_lines = pragma: no cover\n[mutmut]\ndo_not_mutate = x.py\n",
    )
    put(tmp_path, "tox.ini", "[coverage:report]\nexclude_also =\n    def __repr__\n")
    assert config_excludes(tmp_path) == [
        "setup.cfg: coverage omit legacy/*",
        "setup.cfg: coverage exclude_lines pragma: no cover",
        "setup.cfg: mutmut do_not_mutate x.py",
        "tox.ini: coverage exclude_also def __repr__",
    ]


def test_coveragerc_report_settings_count(tmp_path: Path) -> None:
    put(tmp_path, ".coveragerc", "[report]\nexclude_lines =\n    raise NotImplementedError\n")
    assert config_excludes(tmp_path) == [".coveragerc: coverage exclude_lines raise NotImplementedError"]


def test_ini_files_without_the_sections_are_clean(tmp_path: Path) -> None:
    put(tmp_path, "setup.cfg", "[metadata]\nname = x\n")
    put(tmp_path, "tox.ini", "[tox]\nenvlist = py\n")
    assert config_excludes(tmp_path) == []
