"""The real Python plugin, as the entry-point registry finds it."""

import os
import re
import subprocess
import sys
from configparser import ConfigParser
from pathlib import Path

import lizard_languages  # pyright: ignore[reportMissingTypeStubs]
import pytest

from gauntlet import languages
from gauntlet.config import Config
from gauntlet.plugin import Step
from gauntlet_python import LANGUAGE, mutmut
from gauntlet_python.steps import CONFIGURE_MUTMUT, RESULTS_MUTMUT, RUN_MUTMUT, mutants


def test_the_plugin_is_registered_as_python_and_is_the_only_one() -> None:
    assert languages.registry() == {"python": LANGUAGE}


def test_the_row_is_well_formed() -> None:
    row = LANGUAGE
    assert row.suffixes and all(s.startswith(".") and s == s.lower() for s in row.suffixes)
    assert row.markers
    assert re.fullmatch(r"[a-z0-9./:-]+", row.image)
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
    uv = ("uv", "run", "--project", "/tmp/snap")
    env = (("SETUPTOOLS_SCM_PRETEND_VERSION", "0.0.0"),)
    assert LANGUAGE.steps("src", "/tmp/snap", "/tmp/snap/.gauntlet-out", "mutmut", ()) == [
        Step("tests", (*uv, "--with", "pytest-cov==7.1.0", "pytest", "-q", "--cov=src", "--cov-branch",
                       "--cov-report=json:/tmp/snap/.gauntlet-out/coverage.json"), None, 3600, True, env),
        Step("mutation-config", ("python3", "-I", "-c", CONFIGURE_MUTMUT, "/tmp/snap", "src"), None, 60, True, ()),
        Step("mutation", ("python3", "-I", "-c", RUN_MUTMUT, *uv, "--with", "mutmut==3.8.1", "mutmut", "run"),
             None, 7200, False, env),
        Step("mutation-results", (*uv, "--with", "mutmut==3.8.1", "python3", "-I", "-c", RESULTS_MUTMUT),
             "mutmut-results.txt", 1800, True, env),
    ]  # fmt: skip


def test_with_files_in_scope_mutmut_runs_only_their_mutants() -> None:
    plan = LANGUAGE.steps("src", "/p", "/p/out", "mutmut", ("src/pkg/mod.py", "src/pkg/__init__.py"))
    assert plan[2].argv[-6:] == ("mutmut", "run", "pkg.mod.x_*", "pkg.mod.xǁ*", "pkg.x_*", "pkg.xǁ*")
    assert plan[0] == LANGUAGE.steps("src", "/p", "/p/out", "mutmut", ())[0]  # the tests always run in full


@pytest.mark.parametrize(
    ("rel", "module"),
    [
        ("pkg/mod.py", "pkg.mod"),
        ("src/pkg/mod.py", "pkg.mod"),
        ("source/pkg/mod.py", "pkg.mod"),
        ("lib/src/mod.py", "lib.src.mod"),  # only a leading src/ is dropped
        ("pkg/__init__.py", "pkg"),
        ("pkg/__init__/mod.py", "pkg.__init__.mod"),
        ("top.py", "top"),
    ],
)
def test_mutmut_names_a_module_by_its_path(rel: str, module: str) -> None:
    assert mutants((rel,)) == (f"{module}.x_*", f"{module}.xǁ*")


@pytest.mark.parametrize(
    "rel", ["src/__init__.py", "__init__.py", "src.py", "my-pkg/mod.py", "pkg/a b.py", "pkg/2x.py"]
)
def test_a_file_mutmut_cannot_name_gets_no_pattern(rel: str) -> None:
    assert mutants((rel, "ok.py")) == ("ok.x_*", "ok.xǁ*")


def test_no_files_in_scope_means_no_patterns() -> None:
    assert mutants(()) == ()


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


def test_mutmut_is_the_registered_default_tool() -> None:
    assert LANGUAGE.mutation["mutmut"] is mutmut.TOOL
    assert Config.mutation_tool == "mutmut"


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


# A stand-in for `python -m mutmut`: `results` prints the report, `show` a diff for the mutant it is asked about.
FAKE_RESULTS = """
import sys
DIFFS = {
    "p.x_f__mutmut_2": "# p.x_f__mutmut_2: survived\\n--- src/p.py\\n+++ src/p.py\\n@@ -1,3 +1,3 @@\\n def f(a, b):\\n"
                       "-    return a  <\\tb\\n+    return a <= b\\n-    second\\n+    pair\\n",
    "p.x_g__mutmut_1": "# p.x_g__mutmut_1: survived\\n--- src/p.py\\n+++ src/p.py\\n@@ -1,2 +1,1 @@\\n def g():\\n-    gone\\n",
}
if sys.argv[1:] == ["results", "--all", "true"]:
    print("    p.x_f__mutmut_1: killed\\n    p.x_f__mutmut_2: survived\\n    p.x_g__mutmut_1: survived\\n"
          "    p.x_h__mutmut_1: no tests\\n    p.x_i__mutmut_1: survived")
elif sys.argv[1] == "show":
    print(DIFFS.get(sys.argv[2], ""), end="")
    sys.exit(0 if sys.argv[2] in DIFFS else 1)
"""


def _results(tmp_path: Path, fake: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "mutmut.py").write_text(fake)
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    return subprocess.run([sys.executable, "-c", RESULTS_MUTMUT], capture_output=True, text=True, env=env)


def test_each_survivor_is_followed_by_the_line_it_changed(tmp_path: Path) -> None:
    done = _results(tmp_path, FAKE_RESULTS)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "    p.x_f__mutmut_1: killed",
        "    p.x_f__mutmut_2: survived\treturn a < b -> return a <= b",  # the first changed line, spaces tidied
        "    p.x_g__mutmut_1: survived",  # a diff without both sides says nothing
        "    p.x_h__mutmut_1: no tests",
        "    p.x_i__mutmut_1: survived",  # `show` failed: the line is kept as it was
    ]


def test_a_failing_results_command_fails_the_step_with_its_message(tmp_path: Path) -> None:
    done = _results(tmp_path, "import sys; print('no mutants dir', file=sys.stderr); sys.exit(3)")
    assert (done.returncode, done.stdout, done.stderr) == (3, "", "no mutants dir\n")


def test_every_helper_runs_isolated_so_a_project_module_cannot_stand_in_for_the_standard_library(
    tmp_path: Path,
) -> None:
    """The project is the working directory, and `python3 -c` would import its `re.py` before the real one."""
    plan = LANGUAGE.steps("src", "/p", "/p/out", "mutmut", ()) + LANGUAGE.steps("src", "/p", "/p/out", "cosmic-ray", ())
    helpers = [step.argv for step in plan if "-c" in step.argv]
    assert len(helpers) == 6
    for argv in helpers:
        assert argv[argv.index("-c") - 2 : argv.index("-c")] == ("python3", "-I")

    (tmp_path / "re.py").write_text("raise SystemExit('the project hijacked the helper')\n")
    hijacked = subprocess.run([sys.executable, "-c", "import re"], cwd=tmp_path, capture_output=True, text=True)
    assert "hijacked" in hijacked.stderr  # what -I prevents
    assert subprocess.run([sys.executable, "-I", "-c", "import re"], cwd=tmp_path).returncode == 0
