import re
from pathlib import Path

import lizard_languages  # pyright: ignore[reportMissingTypeStubs]
import pytest

from gauntlet import languages, linecov
from gauntlet.names import IMAGE


def test_the_table_is_the_one_list_of_supported_languages() -> None:
    assert set(languages.TABLE) == {"python"}
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
    assert row.artifacts[0] == row.coverage_file
    for suffix in row.suffixes:
        assert lizard_languages.get_reader_for(f"x{suffix}") is not None  # pyright: ignore[reportUnknownMemberType]


def test_get_names_the_supported_languages_on_a_miss() -> None:
    assert languages.get("python") is languages.TABLE["python"]
    with pytest.raises(ValueError, match=r"^unsupported language 'cobol', expected one of python$"):
        languages.get("cobol")


def test_exclusion_pattern_matches_what_python_uses() -> None:
    python = languages.TABLE["python"]
    for text in ("x = 1  # pragma: no cover", "x = 1  # pragma: no mutate", "x  # nosec", "y  #   nosec"):
        assert re.search(python.pragma, text), text
    assert not re.search(python.pragma, "x = 1  # an ordinary comment")


def test_detect_by_marker_files(tmp_path: Path) -> None:
    assert languages.detect(tmp_path) == []
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    assert languages.detect(tmp_path) == ["python"]
    assert languages.detect(tmp_path / "nothing") == []
