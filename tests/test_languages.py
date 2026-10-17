import re
from pathlib import Path

import lizard_languages  # pyright: ignore[reportMissingTypeStubs]
import pytest

from gauntlet import languages, linecov
from gauntlet.clean import function_findings
from gauntlet.exclusions import config_hints
from gauntlet.names import IMAGE


def test_the_table_is_the_one_list_of_supported_languages() -> None:
    assert set(languages.TABLE) >= {"python", "go"}
    assert tuple(languages.TABLE) == languages.NAMES


@pytest.mark.parametrize("name", list(languages.TABLE))
def test_every_row_is_well_formed(name: str) -> None:
    row = languages.TABLE[name]
    assert row.suffixes and all(s.startswith(".") and s == s.lower() for s in row.suffixes)
    assert row.markers or name == "cpp-clang"  # the one row you choose by name
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
        "// Stryker disable next-line all",
        "// STRYKER DISABLE all",
        "//stryker disable-next-line",
        "//Stryker\tdisable all",
        "/* Stryker disable all */",
        "//Stryker disable-next-line EqualityOperator: why",
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
    "// Stryker disable once all",
    "//Stryker disable All : reason",
    "// STRYKER RESTORE all",
    "//stryker disable",
    "// Stryker restore all",
)


@pytest.mark.parametrize("text", CSHARP_HINTS)
def test_csharp_pragma_matches_every_hint_the_coverage_tool_honours(text: str) -> None:
    assert re.search(languages.TABLE["csharp"].pragma, text), text


def test_csharp_pragma_ignores_ordinary_code() -> None:
    text = "// an ordinary comment\n#pragma warning restore CS0168\n// Stryker was here"
    assert not re.search(languages.TABLE["csharp"].pragma, text)


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
        "@DoNotMutate",
        "@CoverageIgnore",
        "  @com.x.CoverageIgnore",
        "  @com.x.DoNotMutate",
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
    assert java.suffixes == (".java",)


RUST_HINTS = (
    "#[coverage(off)]", "#![coverage(off)]", "#[ coverage (off) ]", "#[cfg_attr(coverage_nightly, coverage(off))]",
    "#[no_coverage]", "// LCOV_EXCL_LINE", "// LCOV_EXCL_START", "// LCOV_EXCL_STOP", "// LCOV_EXCL_BR_LINE",
    "#[allow(dead_code)]", "#![allow(clippy::all)]", "#[expect(unused)]", "#[cfg_attr(test, allow(unused))]",
    "#[rustfmt::skip]", "#[rustfmt :: skip]", "#[cfg_attr(rustfmt, rustfmt::skip)]", "#[automatically_derived]",
    "#[mutants::skip]", "#[::mutants::skip]", "#[mutants :: skip]", "#[cfg_attr(test, mutants::skip)]",
    "#![mutants::skip]",
)  # fmt: skip


def test_rust_pragmas_and_test_dirs() -> None:
    rs = languages.TABLE["rust"]
    for text in RUST_HINTS:
        assert re.search(rs.pragma, text), text
    for text in ("// an ordinary comment", "#[derive(Debug)]", "#[cfg(test)]", "#[test]", "// allow this"):
        assert not re.search(rs.pragma, text), text
    assert re.search(rs.tests, "tests/a.rs") and not re.search(rs.tests, "src/tests/a.rs")
    assert not re.search(rs.tests, "src/test/a.rs") and not re.search(rs.tests, "src/a_test.rs")


def test_every_suffix_is_one_lizard_reads() -> None:
    from lizard_languages import get_reader_for  # pyright: ignore

    for name, row in languages.TABLE.items():
        for suffix in row.suffixes:
            assert get_reader_for(f"x.{row.parse_as}" if row.parse_as else f"x{suffix}"), (name, suffix)


UM_HINTS = [  # every way universalmutator leaves a line unmutated
    "x = 1; // DO_NOT_MUTATE",
    "/* DO_NOT_MUTATE */",
    "// @BEGIN_TEST_CODE",
    "// @END_TEST_CODE",
    "if (x > 1) return 1; /* a note",  # code before a /* : the line is skipped, and the rest is a comment
    'glob("src/*.c");',  # a /* in a string starts a "comment" that hides the lines after it
    "end of comment */ if (x > 1) return 1;",  # code after a */ : the closing line is skipped
]


@pytest.mark.parametrize(
    "text",
    [
        *(f"x; // {tool}_EXCL_{kind}" for tool in ("LCOV", "GCOVR") for kind in ("LINE", "START", "STOP")),
        *(f"/* {tool}_EXCL_BR_{kind} */" for tool in ("LCOV", "GCOVR") for kind in ("LINE", "START", "STOP")),
        "int x; // NOLINT",
        "// NOLINTNEXTLINE(readability)",
        '#pragma GCC diagnostic ignored "-Wall"',
        "# pragma  GCC diagnostic push",
        "void f(void) __attribute__((no_instrument_function));",
        "__attribute__ (( no_profile_instrument_function ))",
        *UM_HINTS,
        '#pragma clang diagnostic ignored "-Wall"',
        "if (a == 1) { return 1; } // mull-ignore: cxx_eq_to_ne",
        "// mull-ignore-next: cxx_eq_to_ne",
        "// mull-off",
        "/* mull-off: cxx_all */",
    ],
)
def test_cpp_pragmas_cover_every_exclusion_hint(text: str) -> None:
    for name in ("cpp", "cpp-clang"):
        assert re.search(languages.TABLE[name].pragma, text), text


@pytest.mark.parametrize(
    "text",
    [
        "// an ordinary comment about EXCLUSION\nint x;",
        "/* a plain comment line",
        "/** doc */",
        " * middle */",
        "int mull_off = 1; // mull is a tool",
        "a / b * c;",
    ],
)
def test_cpp_ordinary_code_is_not_a_pragma(text: str) -> None:
    assert not re.search(languages.TABLE["cpp"].pragma, text)


def test_cpp_clang_is_chosen_by_name_and_shares_the_cpp_rules(tmp_path: Path) -> None:
    cpp, clang = languages.TABLE["cpp"], languages.TABLE["cpp-clang"]
    assert clang.markers == ()
    (tmp_path / "CMakeLists.txt").write_text("")
    assert languages.detect(tmp_path) == ["cpp"]  # never picked by detect
    assert languages.get("cpp-clang") is clang
    assert (clang.suffixes, clang.tests, clang.pragma, clang.config_scan) == (
        cpp.suffixes,
        cpp.tests,
        cpp.pragma,
        cpp.config_scan,
    )
    assert (clang.coverage_file, clang.coverage_format) == ("lcov.info", "lcov")
    assert "@sha256:" in clang.image  # the Mull plugin must match this exact clang


def test_a_mull_yml_is_reported_as_a_settings_file(tmp_path: Path) -> None:
    (tmp_path / "mull.yml").write_text("excludePaths: ['.*']\n")
    assert config_hints(tmp_path, "cpp-clang") == ["mull.yml: coverage-affecting settings file"]


def test_cpp_test_dirs_are_top_level_only_and_suffixes_are_lizard_known() -> None:
    cpp = languages.TABLE["cpp"]
    assert re.search(cpp.tests, "tests/a.c") and re.search(cpp.tests, "test/a.cpp")
    assert not re.search(cpp.tests, "src/test/a.c") and not re.search(cpp.tests, "src/a_test.cpp")
    for suffix in cpp.suffixes:
        assert [f.name for f in function_findings("x" + suffix, "int f(int x) { return x; }\n", None)] == ["f"], suffix


def _lizard_reads(filename: str) -> bool:
    return lizard_languages.get_reader_for(filename) is not None  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.parametrize("name", list(languages.TABLE))
def test_lizard_reads_every_suffix_directly_or_through_the_named_reader(name: str) -> None:
    row = languages.TABLE[name]
    for suffix in row.suffixes:
        assert _lizard_reads(f"x.{row.parse_as}" if row.parse_as else f"x{suffix}"), suffix


def test_dart_row_and_test_dirs() -> None:
    dart = languages.TABLE["dart"]
    assert (dart.suffixes, dart.markers, dart.coverage_format) == (
        (".dart",), ("pubspec.yaml",), "lcov"
    )  # fmt: skip
    assert re.search(dart.tests, "test/a_test.dart")
    for path in ("lib/test/a.dart", "lib/a_test.dart", "tests/a.dart", "test.dart"):
        assert not re.search(dart.tests, path), path


@pytest.mark.parametrize(
    "text",
    [
        "x(); // coverage:ignore-line",
        "// coverage:ignore-start",
        "// coverage:ignore-end",
        "// coverage:ignore-file",
        "int a = b!; // ignore: unnecessary_non_null_assertion",
        "// ignore_for_file: unused_element",
        "// dart format off",
        "// dart format on",
        "//coverage:ignore-line",
        "/// ignore: x",
    ],
)
def test_every_dart_ignore_hint_is_a_pragma(text: str) -> None:
    assert re.search(languages.TABLE["dart"].pragma, text), text


def test_ordinary_dart_comments_are_not_pragmas() -> None:
    for text in ("// coverage is good", "// we ignore nothing", "// format the dart"):
        assert not re.search(languages.TABLE["dart"].pragma, text), text


@pytest.mark.parametrize(
    ("language", "hidden", "plain"),
    [
        ("cpp", ["x; // GCOV_EXCL_LINE", "// LCOVR_EXCL_START", "// GCOVR_EXCL_BR_SOURCE"], ["int gcov_excl = 1;"]),
        ("cpp-clang", ["x; // GCOV_EXCL_LINE", "// mull-off", "x; // mull-ignore: cxx_all"], ["int gcov_excl = 1;"]),
        (
            "rust",
            [
                "# [coverage(off)]",
                "#[cfg(not(coverage))]",
                "#[cfg_attr(coverage_nightly, coverage(off))]",
                "#[cfg_attr(",
                "#![allow(dead_code)]",
                '#[cfg_attr(feature = "a]", allow(dead_code))]',
            ],
            ['#[cfg_attr(feature = "x", derive(Debug))]', "#[derive(Debug)]", "#[cfg(test)]"],
        ),
    ],
)
def test_pragmas_cover_every_spelling_the_tool_honours(language: str, hidden: list[str], plain: list[str]) -> None:
    pattern = languages.TABLE[language].pragma
    for text in hidden:
        assert re.search(pattern, text), text
    for text in plain:
        assert not re.search(pattern, text), text


def test_java_config_scan_reports_a_pitest_block_in_the_pom() -> None:
    (glob, pattern), *_ = languages.TABLE["java"].config_scan
    assert glob == "pom.xml"
    for text in ("<artifactId>pitest-maven</artifactId>", "<groupId>org.pitest</groupId>"):
        assert re.search(pattern, text), text
    assert not re.search(pattern, "<artifactId>junit-jupiter</artifactId>")
