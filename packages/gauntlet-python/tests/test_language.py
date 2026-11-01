"""The real Python plugin, as the entry-point registry finds it."""

import re
from pathlib import Path

import lizard_languages  # pyright: ignore[reportMissingTypeStubs]

from gauntlet import languages
from gauntlet.plugin import Step
from gauntlet_python import LANGUAGE
from gauntlet_sandbox.names import IMAGE


def test_the_plugin_is_registered_as_python_and_is_the_only_one() -> None:
    assert languages.registry() == {"python": LANGUAGE}


def test_the_row_is_well_formed() -> None:
    row = LANGUAGE
    assert row.suffixes and all(s.startswith(".") and s == s.lower() for s in row.suffixes)
    assert row.markers
    assert IMAGE.match(row.image)
    assert re.compile(row.pragma)  # a valid exclusion pattern
    assert "/" not in row.coverage_file
    assert row.artifacts[0] == row.coverage_file
    for suffix in row.suffixes:
        assert lizard_languages.get_reader_for(f"x{suffix}") is not None  # pyright: ignore[reportUnknownMemberType]


def test_exclusion_pattern_matches_what_python_uses() -> None:
    for text in ("x = 1  # pragma: no cover", "x = 1  # pragma: no mutate", "x  # nosec", "y  #   nosec"):
        assert re.search(LANGUAGE.pragma, text), text
    assert not re.search(LANGUAGE.pragma, "x = 1  # an ordinary comment")


def test_detect_by_marker_files(tmp_path: Path) -> None:
    assert languages.detect(tmp_path) == []
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    assert languages.detect(tmp_path) == ["python"]


def test_python_steps_in_full() -> None:
    assert LANGUAGE.steps("src", "/project/.gauntlet-out") == [
        Step(
            "tests",
            ("uv", "run", "--project", "/project", "--with", "pytest-cov==7.1.0", "pytest", "-q", "--cov=src",
             "--cov-branch", "--cov-report=json:/project/.gauntlet-out/coverage.json"),
            None,
            3600,
            True,
            (),
        ),
        Step(
            "mutation",
            ("uv", "run", "--project", "/project", "--with", "mutmut==3.8.0", "mutmut", "run"),
            None,
            7200,
            False,
            (),
        ),
        Step(
            "mutation-results",
            ("uv", "run", "--project", "/project", "--with", "mutmut==3.8.0", "mutmut", "results", "--all", "true"),
            "mutmut-results.txt",
            1800,
            True,
            (),
        ),
    ]  # fmt: skip


def test_the_python_mutation_reader_is_registered() -> None:
    tool = LANGUAGE.mutation
    assert tool.read("p.x: killed\np.y: survived\n").pct == 50.0
    assert tool.artifact == "mutmut-results.txt"
