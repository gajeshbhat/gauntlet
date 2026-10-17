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


def test_javascript_pragmas_and_test_dirs() -> None:
    js = languages.TABLE["javascript"]
    for text in ("/* istanbul ignore next */", "// c8 ignore next", "// eslint-disable-next-line", "// @ts-ignore"):
        assert re.search(js.pragma, text), text
    assert not re.search(js.pragma, "// an ordinary comment")
    assert re.search(js.tests, "tests/a.js") and not re.search(js.tests, "src/tests/a.js")


def test_every_row_names_a_known_coverage_format_and_a_valid_image() -> None:
    for name, row in languages.TABLE.items():
        assert row.coverage_format in linecov.PARSERS, name
        assert IMAGE.match(row.image), name
