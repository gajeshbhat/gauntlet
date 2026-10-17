import re
from pathlib import Path

import pytest

from gauntlet import languages, linecov
from gauntlet.names import IMAGE


def test_the_table_is_the_one_list_of_supported_languages() -> None:
    assert set(languages.TABLE) >= {"python", "go"}
    assert tuple(languages.TABLE) == languages.NAMES


@pytest.mark.parametrize("name", list(languages.TABLE))
def test_every_row_is_well_formed(name: str) -> None:
    row = languages.TABLE[name]
    assert row.suffixes and all(s.startswith(".") and s == s.lower() for s in row.suffixes)
    assert row.markers
    assert row.coverage_format in linecov.PARSERS
    assert IMAGE.match(row.image)
    assert re.compile(row.pragma)  # a valid exclusion pattern
    assert "/" not in row.coverage_file


def test_get_names_the_supported_languages_on_a_miss() -> None:
    assert languages.get("go") is languages.TABLE["go"]
    with pytest.raises(ValueError, match=r"^unsupported language 'cobol', expected one of "):
        languages.get("cobol")


def test_exclusion_patterns_match_what_each_language_uses() -> None:
    python, go = languages.TABLE["python"], languages.TABLE["go"]
    for text in ("x = 1  # pragma: no cover", "x = 1  # pragma: no mutate", "x  # nosec", "y  #   nosec"):
        assert re.search(python.pragma, text), text
    for text in ("f() //nolint", "f() // nolint:gocyclo"):
        assert re.search(go.pragma, text), text
    assert not re.search(python.pragma, "x = 1  # an ordinary comment")
    assert not re.search(go.pragma, "// an ordinary comment")


def test_detect_by_marker_files(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module m\n")
    assert languages.detect(tmp_path) == ["go"]
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    assert languages.detect(tmp_path) == ["python", "go"]
    assert languages.detect(tmp_path / "nothing") == []


def test_dotnet_projects_are_detected_by_their_project_or_solution_file(tmp_path: Path) -> None:
    (tmp_path / "App.sln").write_text("")
    assert languages.detect(tmp_path) == ["csharp"]
    (tmp_path / "App.sln").unlink()
    (tmp_path / "App.csproj").write_text("")
    assert languages.detect(tmp_path) == ["csharp"]


def test_javascript_pragmas_and_test_dirs() -> None:
    js = languages.TABLE["javascript"]
    for text in (
        "/* istanbul ignore next */",
        "// c8 ignore next",
        "// eslint-disable-next-line",
        "// @ts-ignore",
        "/* v8 ignore next */",
        "// node:coverage ignore next",
        "// node:coverage disable",
    ):
        assert re.search(js.pragma, text), text
    assert not re.search(js.pragma, "// an ordinary comment")
    assert re.search(js.tests, "tests/a.js") and not re.search(js.tests, "src/tests/a.js")


def test_every_row_names_a_known_coverage_format_and_a_valid_image() -> None:
    for name, row in languages.TABLE.items():
        assert row.coverage_format in linecov.PARSERS, name
        assert IMAGE.match(row.image), name


CSHARP_HINTS = (
    "[ExcludeFromCodeCoverage]",
    '[System.Diagnostics.CodeAnalysis.ExcludeFromCodeCoverage(Justification = "x")]',
    "[ExcludeFromCodeCoverageAttribute]",
    "[ExcludeFromCoverage]",
    "[ExcludeFromCoverageAttribute]",
    "[Serializable, ExcludeFromCodeCoverage]",
    "    ExcludeFromCodeCoverage,",
    "[assembly: ExcludeFromCodeCoverage]",
    '[GeneratedCode("tool", "1.0")]',
    "[CompilerGenerated]",
    "#pragma warning disable CS0168",
    "  #  pragma warning disable",
    "x++; //codecov:ignore",
    "// codecov ignore",
)


@pytest.mark.parametrize("text", CSHARP_HINTS)
def test_csharp_pragma_matches_every_hint_the_coverage_tool_honours(text: str) -> None:
    assert re.search(languages.TABLE["csharp"].pragma, text), text


def test_csharp_pragma_ignores_ordinary_code() -> None:
    assert not re.search(languages.TABLE["csharp"].pragma, "// an ordinary comment\n#pragma warning restore CS0168")


def test_csharp_test_dirs_are_only_the_top_level_ones() -> None:
    cs = languages.TABLE["csharp"]
    for path in ("tests/App.Tests/A.cs", "test/A.cs", "Tests/A.cs"):
        assert re.search(cs.tests, path), path
    for path in ("src/tests/A.cs", "src/App/FooTests.cs", "src/Test/A.cs", "mytests/A.cs", "src/App/Tests.cs"):
        assert not re.search(cs.tests, path), path


def test_java_pragmas_cover_every_hint_the_pinned_jacoco_and_linters_honour() -> None:
    java = languages.TABLE["java"]
    for text in (
        "@Generated",
        "  @lombok.Generated",
        '@javax.annotation.processing.Generated("x")',
        "@GeneratedByTool",
        '@SuppressWarnings("unchecked")',
        "x++; // NOSONAR",
        "x++; //NOPMD",
        "// CHECKSTYLE:OFF",
        "//CHECKSTYLE:OFF",
        "// @formatter:off",
        "//@formatter:off",
    ):
        assert re.search(java.pragma, text), text
    assert not re.search(java.pragma, "// an ordinary comment")
    assert not re.search(java.pragma, "int generated = 1;")


def test_java_tests_are_only_the_top_level_test_dirs() -> None:
    java = languages.TABLE["java"]
    for path in ("src/test/java/a/ATest.java", "test/a/ATest.java", "tests/A.java"):
        assert re.search(java.tests, path), path
    for path in ("src/main/java/ATest.java", "src/main/test/A.java", "src/tests/A.java", "app/src/main/java/Test.java"):
        assert not re.search(java.tests, path), path
    assert not java.mutation
    assert java.suffixes == (".java",)
