"""cppmutants.py runs inside the sandbox; here the tools it drives are stubbed. The real run is in test_docker_real."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from gauntlet import cppmutants

TESTS = r"^tests?/"


def tree(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def test_sources_are_the_languages_suffixes_minus_tests_and_our_own_directories(tmp_path: Path) -> None:
    names = ["src/b.c", "src/a.cpp", "inc/x.h", "tests/t.c", "test/u.cc", "src/test/keep.c", "README.md",
             ".git/hooks.c", ".gauntlet-out/gen.c"]  # fmt: skip
    tree(tmp_path, dict.fromkeys(names, ""))
    found = cppmutants.sources(tmp_path, (".c", ".cc", ".cpp", ".h"), TESTS)
    assert found == ["inc/x.h", "src/a.cpp", "src/b.c", "src/test/keep.c"]


def test_only_the_top_level_output_directory_is_skipped(tmp_path: Path) -> None:
    tree(tmp_path, {".gauntlet-out/gen.c": "", "src/.gauntlet-out/real.c": "", "src/a.c": ""})
    assert cppmutants.sources(tmp_path, (".c",), TESTS) == ["src/a.c", "src/.gauntlet-out/real.c"]


def test_run_passes_and_a_failing_tool_stops_the_script_with_its_output_tail(tmp_path: Path) -> None:
    cppmutants.run(["true"], tmp_path)
    with pytest.raises(SystemExit, match=r"sh failed \(exit 3\): oops \| said"):
        cppmutants.run(["sh", "-c", "echo said; echo oops >&2; exit 3"], tmp_path)


def test_the_tools_run_isolated_from_the_current_directory() -> None:
    argv = cppmutants.module("analyze", "a.c")
    assert argv[1:] == ["-P", "-m", "universalmutator.analyze", "a.c"]


def test_commands_are_quoted_and_a_build_failure_is_not_a_kill() -> None:
    build = cppmutants.build_command("/o u/cmake", "/o u/b")
    test = cppmutants.test_command("/o u/ctest", "/o u/b")
    assert build == "'/o u/cmake' --build '/o u/b' >/dev/null 2>&1"
    assert test == "'/o u/ctest' --test-dir '/o u/b' --timeout 120 >/dev/null 2>&1"


def test_change_names_the_line_and_what_became_of_it(tmp_path: Path) -> None:
    mutant = tmp_path / "m.c"
    mutant.write_text("int a;\nif (x > 1)  \n")
    assert cppmutants.change("int a;\n  if (x >= 1)\n", mutant) == (2, "if (x >= 1) -> if (x > 1)")
    mutant.write_text("int a;\n" + "x" * 200 + "\n")
    assert cppmutants.change("int a;\ny\n", mutant) == (2, "y -> " + "x" * 80)
    mutant.write_text("same\n")
    with pytest.raises(SystemExit, match=r"m\.c does not differ"):
        cppmutants.change("same\n", mutant)


SOURCE = "int f(int x) {\n  return x > 1;\n}\n"


def fake_run(
    killed: str, survived: str, *, make: tuple[str, ...] = ("f.mutant.0.c", "f.mutant.1.c"), clobber: bool = True
):  # type: ignore[no-untyped-def]  # noqa: ANN201
    calls: list[list[str]] = []

    def run(argv: list[str], cwd: Path) -> None:
        calls.append(argv)
        source = Path(argv[4])
        if argv[3].endswith("genmutants"):
            for name in make:
                (cwd / name).write_text(SOURCE.replace(">", "<" if name.endswith("0.c") else ">="))
        else:
            if clobber:
                source.write_text("mutant in place")
            (cwd / "killed.txt").write_text(killed)
            (cwd / "notkilled.txt").write_text(survived)

    return run, calls


def test_analyse_reports_every_mutant_as_killed_or_survived_and_puts_the_source_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree(tmp_path, {"src/f.c": SOURCE})
    run, calls = fake_run("f.mutant.0.c\n", "f.mutant.1.c\n")
    monkeypatch.setattr(cppmutants, "run", run)
    rows = cppmutants.analyse("src/f.c", tmp_path / "w", tmp_path, "BUILD", "TEST")
    assert rows == [
        {"file": "src/f.c", "line": 2, "mutation": "return x > 1; -> return x < 1;", "status": "killed"},
        {"file": "src/f.c", "line": 2, "mutation": "return x > 1; -> return x >= 1;", "status": "survived"},
    ]
    assert (tmp_path / "src/f.c").read_text() == SOURCE
    gen, analyze = calls
    assert gen[4:] == [str(tmp_path / "src/f.c"), "--cmd", "BUILD", "--mutantDir", str(tmp_path / "w")]
    assert analyze[4:7] == [str(tmp_path / "src/f.c"), "BUILD || exit 0; TEST", "--mutantDir"]
    assert analyze[-3:] == ["--noShuffle", "--timeout", "1800"]
    assert "--seed" not in analyze and "--numMutants" not in analyze  # no mutant is dropped


def test_a_partial_analysis_is_an_error_not_a_score(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree(tmp_path, {"src/f.c": SOURCE})
    run, _ = fake_run("f.mutant.0.c\n", "")  # mutant 1 was never analysed
    monkeypatch.setattr(cppmutants, "run", run)
    with pytest.raises(SystemExit, match=r"src/f\.c: 2 mutants made, 1 analysed: partial run"):
        cppmutants.analyse("src/f.c", tmp_path / "w", tmp_path, "B", "T")
    assert (tmp_path / "src/f.c").read_text() == SOURCE  # restored on the way out


def test_a_crashed_analysis_still_restores_the_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree(tmp_path, {"src/f.c": SOURCE})

    def run(argv: list[str], cwd: Path) -> None:  # noqa: ARG001
        if argv[3].endswith("analyze"):
            Path(argv[4]).write_text("mutant in place")
            raise SystemExit("analyze failed")

    monkeypatch.setattr(cppmutants, "run", run)
    with pytest.raises(SystemExit, match="analyze failed"):
        cppmutants.analyse("src/f.c", tmp_path / "w", tmp_path, "B", "T")
    assert (tmp_path / "src/f.c").read_text() == SOURCE


def test_main_configures_checks_the_baseline_and_writes_one_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree(
        tmp_path, {"src/f.c": SOURCE, "src/g.c": SOURCE, "tests/t.c": "", "out/mutwork/stale": "", "out/mutbuild/x": ""}
    )
    seen: list[list[str]] = []

    def record(argv: list[str], cwd: Path) -> None:  # noqa: ARG001
        seen.append(argv)

    def analyse(rel: str, work: Path, root: Path, build: str, test: str) -> list[dict[str, object]]:  # noqa: ARG001
        return [{"file": rel, "work": work.name, "test": test}]

    monkeypatch.setattr(cppmutants, "run", record)
    monkeypatch.setattr(cppmutants, "analyse", analyse)
    report = tmp_path / "report.json"
    argv = [str(tmp_path), str(tmp_path / "out"), str(report), ".c,.h", TESTS, "-DA=1", "-DB=2"]
    assert cppmutants.main(argv) == 0
    configure, baseline = seen
    cmake, build = str(tmp_path / "out/py/bin/cmake"), str(tmp_path / "out/mutbuild")
    assert configure == [cmake, "-S", str(tmp_path), "-B", build, "-DCMAKE_BUILD_TYPE=Debug", "-DA=1", "-DB=2"]
    assert baseline[:2] == ["sh", "-c"] and baseline[2].count(" && ") == 1 and "--build" in baseline[2]
    assert not (tmp_path / "out/mutwork").exists() and not (tmp_path / "out/mutbuild").exists()
    rows = json.loads(report.read_text())["mutants"]
    assert [(r["file"], r["work"]) for r in rows] == [("src/f.c", "0"), ("src/g.c", "1")]


def test_running_the_file_as_a_script_exits_with_main_s_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["cppmutants.py"])
    with pytest.raises(ValueError, match="not enough values"):  # no arguments: main refuses before doing anything
        runpy.run_path(cppmutants.__file__, run_name="__main__")
