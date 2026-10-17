from pathlib import Path

import pytest

from gauntlet.exclusions import config_excludes, config_hints, pragmas
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


def test_include_and_omit_settings_that_narrow_coverage_are_exclusions(tmp_path: Path) -> None:
    put(
        tmp_path,
        "pyproject.toml",
        '[tool.coverage.run]\ninclude = ["src/only/*"]\n[tool.coverage.report]\nomit = ["src/old/*"]\ninclude = ["src/new/*"]\n',
    )
    put(tmp_path, ".coveragerc", "[run]\ninclude = a/*\n[report]\nomit = b/*\ninclude = c/*\n")
    assert config_excludes(tmp_path) == [
        "pyproject.toml: coverage run include src/only/*",
        "pyproject.toml: coverage report omit src/old/*",
        "pyproject.toml: coverage report include src/new/*",
        ".coveragerc: coverage run include a/*",
        ".coveragerc: coverage report omit b/*",
        ".coveragerc: coverage report include c/*",
    ]


@pytest.mark.parametrize(
    ("language", "name", "text", "expected"),
    [
        ("javascript", ".c8rc.json", "{}", [".c8rc.json: coverage-affecting settings file"]),
        (
            "javascript",
            "package.json",
            '{\n  "c8": {"exclude": ["a"]}\n}',
            ['package.json:2: "c8": {"exclude": ["a"]}'],
        ),
        ("javascript", "package.json", '{"name": "x"}', []),
        (
            "csharp",
            "app/Tests.runsettings",
            "<RunSettings/>",
            ["app/Tests.runsettings: coverage-affecting settings file"],
        ),
        (
            "csharp",
            "src/A.csproj",
            "<TreatAsLocalProperty>RunSettingsFilePath</TreatAsLocalProperty>",
            ["src/A.csproj:1: <TreatAsLocalProperty>RunSettingsFilePath</TreatAsLocalProperty>"],
        ),
        ("csharp", "src/A.csproj", '<PackageReference Include="coverlet.collector" />', []),
        (
            "java",
            "pom.xml",
            "<plugin>jacoco-maven-plugin</plugin>",
            ["pom.xml:1: <plugin>jacoco-maven-plugin</plugin>"],
        ),
        ("java", ".mvn/maven.config", "-DskipTests", [".mvn/maven.config: coverage-affecting settings file"]),
        ("rust", ".cargo/config.toml", "[build]", [".cargo/config.toml: coverage-affecting settings file"]),
        ("rust", "rust-toolchain.toml", "nightly", ["rust-toolchain.toml: coverage-affecting settings file"]),
        ("rust", "Cargo.toml", "[package]", []),
        ("dart", "dart_test.yaml", "exclude_tags: slow", ["dart_test.yaml:1: exclude_tags: slow"]),
        ("cpp", "CMakeLists.txt", "project(x)", []),
    ],
)
def test_config_hints_find_settings_that_can_hide_code(
    tmp_path: Path, language: str, name: str, text: str, expected: list[str]
) -> None:
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(text)
    assert config_hints(tmp_path, language) == expected


def test_config_hints_skip_vendored_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / ".c8rc.json").write_text("{}")
    assert config_hints(tmp_path, "javascript") == []
