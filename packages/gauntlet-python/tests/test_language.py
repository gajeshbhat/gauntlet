"""The real Python plugin, as the entry-point registry finds it."""

import re
import subprocess
import sys
from configparser import ConfigParser
from pathlib import Path

import lizard_languages  # pyright: ignore[reportMissingTypeStubs]
import pytest

from gauntlet import languages
from gauntlet.plugin import Step
from gauntlet_python import LANGUAGE
from gauntlet_python.steps import CONFIGURE_MUTMUT, RUN_MUTMUT
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


VARIANTS = ("# pragma no cover", "# pragma:nocover", "# PRAGMA: NO COVER", "#pragma nocover", "# pragma: no branch")


def test_exclusion_pattern_catches_every_variant_coverage_py_honours() -> None:
    from coverage.config import DEFAULT_EXCLUDE  # pyright: ignore[reportMissingTypeStubs]

    for text in VARIANTS:
        assert re.search(LANGUAGE.pragma, text), text
    for default in (d for d in DEFAULT_EXCLUDE if "pragma" in d):
        for text in VARIANTS[:4]:
            assert re.search(default, text), (default, text)  # the variants really are ones coverage.py skips


def test_detect_by_marker_files(tmp_path: Path) -> None:
    assert languages.detect(tmp_path) == []
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    assert languages.detect(tmp_path) == ["python"]


def test_python_steps_in_full() -> None:
    uv = ("uv", "run", "--project", "/project")
    env = (("SETUPTOOLS_SCM_PRETEND_VERSION", "0.0.0"),)
    assert LANGUAGE.steps("src", "/project/.gauntlet-out", "mutmut") == [
        Step("tests", (*uv, "--with", "pytest-cov==7.1.0", "pytest", "-q", "--cov=src", "--cov-branch",
                       "--cov-report=json:/project/.gauntlet-out/coverage.json"), None, 3600, True, env),
        Step("mutation-config", ("python3", "-c", CONFIGURE_MUTMUT, "/project", "src"), None, 60, True, ()),
        Step("mutation", ("python3", "-c", RUN_MUTMUT, *uv, "--with", "mutmut==3.8.1", "mutmut", "run"), None, 7200, False, env),
        Step("mutation-results", (*uv, "--with", "mutmut==3.8.1", "mutmut", "results", "--all", "true"),
             "mutmut-results.txt", 1800, True, env),
    ]  # fmt: skip


def _configure(root: Path, src: str) -> None:
    subprocess.run([sys.executable, "-c", CONFIGURE_MUTMUT, str(root), src], check=True)


def test_mutmut_is_pointed_at_the_source_when_the_project_does_not_say(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    _configure(tmp_path, "pkg")
    config = ConfigParser()
    config.read(tmp_path / "setup.cfg")
    assert config["mutmut"]["source_paths"] == "pkg"
    assert "*/tests/*" in config["mutmut"]["do_not_mutate"]


@pytest.mark.parametrize(
    ("name", "text"),
    [("pyproject.toml", "[tool.mutmut]\nsource_paths = ['mine']\n"), ("setup.cfg", "[mutmut]\nsource_paths = mine\n")],
)
def test_a_projects_own_mutmut_config_is_left_alone(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / name).write_text(text)
    _configure(tmp_path, "pkg")
    assert (tmp_path / name).read_text() == text
    assert not (tmp_path / "setup.cfg").exists() or name == "setup.cfg"


def test_the_python_mutation_reader_is_registered() -> None:
    tool = LANGUAGE.mutation["mutmut"]
    assert tool.read("p.x: killed\np.y: survived\n").pct == 50.0
    assert tool.artifact == "mutmut-results.txt"


FAKE_MUTMUT = """
import os, sys
if "--deselect=tests/test_a.py::test_breaks" in os.environ.get("PYTEST_ADDOPTS", ""):
    print("done")
else:
    print("FAILED tests/test_a.py::test_breaks - boom\\nfailed to collect stats. runner returned 1")
    sys.exit(1)
"""


def _run_mutmut(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", RUN_MUTMUT, *command], capture_output=True, text=True)


def test_a_test_that_breaks_under_mutation_is_deselected_and_mutmut_retried() -> None:
    done = _run_mutmut([sys.executable, "-c", FAKE_MUTMUT])
    assert done.returncode == 0
    assert "deselected tests/test_a.py::test_breaks" in done.stderr


def test_a_failure_that_names_no_new_test_is_left_to_fail() -> None:
    done = _run_mutmut([sys.executable, "-c", "import sys; print('failed to collect stats'); sys.exit(3)"])
    assert done.returncode == 3


FAKE_CLEAN_RUN = """
import os, sys
if "--deselect=tests/test_a.py::test_flaky" in os.environ.get("PYTEST_ADDOPTS", ""):
    print("done")
else:
    print("FAILED tests/test_a.py::test_flaky - boom\\nFailed to run clean test")
    sys.exit(1)
"""


def test_a_test_that_fails_mutmut_clean_run_is_deselected_too() -> None:
    done = _run_mutmut([sys.executable, "-c", FAKE_CLEAN_RUN])
    assert done.returncode == 0
    assert "deselected tests/test_a.py::test_flaky" in done.stderr


FAKE_PARAMETRIZED = """
import os, sys
if "--deselect=tests/test_a.py::test_p " in os.environ.get("PYTEST_ADDOPTS", "") + " ":
    print("done")
else:
    print("FAILED tests/test_a.py::test_p[3-Foo] - boom\\nfailed to collect stats. runner returned 1")
    sys.exit(1)
"""


def test_a_failing_parametrized_test_is_deselected_whole_in_one_retry() -> None:
    done = _run_mutmut([sys.executable, "-c", FAKE_PARAMETRIZED])
    assert done.returncode == 0
    assert "deselected tests/test_a.py::test_p\n" in done.stderr
