import pytest

from gauntlet import linecov

COVERAGEPY = '{"files": {"src/a.py": {"executed_lines": [1, 2], "missing_lines": [4]}}}'
GOCOVER = """mode: set
example.com/m/pkg/a.go:3.10,5.2 2 1
example.com/m/pkg/a.go:7.14,9.2 1 0
"""
LCOV = """TN:
SF:src/a.js
FN:1,f
DA:1,3
DA:2,0
DA:4,1
end_of_record
SF:/project/src/b.js
DA:1,0
end_of_record
"""
COBERTURA = """<?xml version="1.0"?>
<coverage><packages><package><classes>
<class filename="src/Foo.cs"><lines><line number="3" hits="2"/><line number="4" hits="0"/></lines></class>
</classes></package></packages></coverage>
"""
JACOCO = """<?xml version="1.0"?>
<report name="x"><package name="com/x"><sourcefile name="Foo.java">
<line nr="3" mi="0" ci="4" mb="0" cb="0"/><line nr="4" mi="2" ci="0" mb="0" cb="0"/><line nr="6" mi="0" ci="0" mb="0" cb="0"/>
</sourcefile></package></report>
"""


def test_coveragepy() -> None:
    assert linecov.parse("coveragepy", COVERAGEPY) == {"src/a.py": {1: 1, 2: 1, 4: 0}}


def test_go_profile_marks_every_line_of_a_block() -> None:
    lines = linecov.parse("gocover", GOCOVER)
    assert lines == {"example.com/m/pkg/a.go": {3: 1, 4: 1, 5: 1, 7: 0, 8: 0, 9: 0}}


def test_go_profile_counts_a_line_hit_if_any_block_on_it_ran() -> None:
    text = "mode: set\nm/a.go:3.1,3.9 1 0\nm/a.go:3.10,4.2 1 1\n"
    assert linecov.parse("gocover", text) == {"m/a.go": {3: 1, 4: 1}}


def test_lcov_keeps_absolute_paths_as_written() -> None:
    assert linecov.parse("lcov", LCOV) == {"src/a.js": {1: 3, 2: 0, 4: 1}, "/project/src/b.js": {1: 0}}


def test_cobertura() -> None:
    assert linecov.parse("cobertura", COBERTURA) == {"src/Foo.cs": {3: 2, 4: 0}}


def test_jacoco_only_lines_with_instructions_are_executable() -> None:
    assert linecov.parse("jacoco", JACOCO) == {"com/x/Foo.java": {3: 4, 4: 0}}


@pytest.mark.parametrize("fmt", ["cobertura", "jacoco"])
def test_xml_with_entities_or_doctype_is_refused(fmt: str) -> None:
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><coverage>&a;</coverage>'
    with pytest.raises(ValueError, match="DOCTYPE or entity"):
        linecov.parse(fmt, evil)


@pytest.mark.parametrize("fmt", ["cobertura", "jacoco"])
def test_malformed_xml_is_a_clean_error(fmt: str) -> None:
    with pytest.raises(ValueError, match=f"cannot read {fmt} report"):
        linecov.parse(fmt, "<coverage><oops>")


@pytest.mark.parametrize(
    ("fmt", "text"),
    [
        ("coveragepy", "garbage: [[["),
        ("coveragepy", '{"files": {"a.py": {}}}'),
        ("gocover", "mode: set\nnot a block\n"),
        ("lcov", "DA:notanumber,x\n"),
    ],
)
def test_malformed_text_reports_are_clean_errors(fmt: str, text: str) -> None:
    with pytest.raises(ValueError, match=f"^cannot read {fmt} report$"):
        linecov.parse(fmt, text)


def test_unknown_format() -> None:
    with pytest.raises(ValueError, match=r"^unknown coverage format 'xyz'"):
        linecov.parse("xyz", "")


def test_empty_reports_are_empty_not_errors() -> None:
    assert linecov.parse("lcov", "") == {}
    assert linecov.parse("gocover", "mode: set\n") == {}


@pytest.mark.parametrize(
    ("key", "files", "expected"),
    [
        ("src/a.py", ["src/a.py", "src/b.py"], "src/a.py"),
        ("example.com/m/pkg/a.go", ["pkg/a.go", "other/a.go"], "pkg/a.go"),
        ("com/x/Foo.java", ["src/main/java/com/x/Foo.java"], "src/main/java/com/x/Foo.java"),
        ("/project/src/b.js", ["src/b.js"], "src/b.js"),
        ("/home/me/proj/src/b.js", ["src/b.js"], "src/b.js"),
    ],
)
def test_coverage_paths_match_source_files_by_path_suffix(key: str, files: list[str], expected: str) -> None:
    assert linecov.locate(key, files) == expected


def test_a_name_that_only_ends_the_same_is_not_a_match() -> None:
    assert linecov.locate("a.go", ["pkg/data.go", "pkg/beta.go"]) is None


def test_ambiguous_suffix_is_an_error() -> None:
    with pytest.raises(ValueError, match="matches more than one file"):
        linecov.locate("a.go", ["x/a.go", "y/a.go"])


@pytest.mark.parametrize("key", ["../secret.py", "a/../../secret.py", "/project/../etc/passwd"])
def test_paths_that_climb_out_are_refused(key: str) -> None:
    with pytest.raises(ValueError, match="escapes the project root"):
        linecov.locate(key, ["secret.py"])
