import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from cli_helpers import (
    Out,
    RunSandbox,
    committed_py_project,
    git,
    project,
    sandbox_factory,
)

from gauntlet import cli
from gauntlet.cli import main
from gauntlet.sandbox import ExecResult


# ---- run (sandboxed pipeline)
def test_run_produces_artifacts_in_the_sandbox_then_evaluates_every_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["run", str(root)]) == 0
    out = capsys.readouterr().out
    assert "produced coverage.json, mutmut-results.txt" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "exclusions:" in out
    assert "mutation score 90.0% >= 90%" in out
    assert (root / ".gauntlet" / "gauntlet-manifest.json").exists()


def test_run_fails_when_a_gate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory(covered=False))
    assert main(["run", str(root)]) == 1


def test_run_honours_out_and_ignores_stale_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path / "repo") if (tmp_path / "repo").mkdir() is None else tmp_path
    (root / "coverage.json").write_text('{"files": {}}')  # stale junk next to the sources must not matter
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    out = tmp_path / "elsewhere"
    assert main(["run", str(root), "--out", str(out)]) == 0
    assert (out / "coverage.json").exists()
    capsys.readouterr()


def test_gates_default_to_the_results_of_the_last_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["run", str(root)]) == 0
    capsys.readouterr()
    assert main(["clean", str(root)]) == 0  # finds .gauntlet/ by itself: stamped, so it verifies
    (root / "mod.py").write_text("def g():\n    return 2\n")
    assert main(["clean", str(root)]) == 2
    assert "stale" in capsys.readouterr().err


def test_stamp_never_blesses_the_results_of_an_old_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory(covered=False))
    assert main(["run", str(root)]) == 1  # leaves .gauntlet/ with uncovered results
    capsys.readouterr()
    covered = {"mod.py": {"executed_lines": list(range(1, 17)), "missing_lines": []}}
    (root / "coverage.json").write_text(json.dumps({"files": covered}))  # fresh artifacts next to the sources
    assert main(["stamp", str(root)]) == 0
    assert "stamped coverage.json" in capsys.readouterr().out
    assert (root / "gauntlet-manifest.json").exists()
    assert main(["clean", str(root), "--artifacts", str(root)]) == 0  # the fresh ones, not the old run's


# ---- Rust: lcov with absolute container paths
class RustSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if "--lcov" in argv:
            lcov = "SF:/project/src/lib.rs\nDA:1,1\nDA:2,1\nend_of_record\n"
            (self.project / ".gauntlet-out" / "lcov.info").write_text(lcov)
        if "--no-config" in argv:
            report = '{"total_mutants": 1, "outcomes": [{"scenario": {"Mutant": {"file": "src/lib.rs", "replacement": "0", "genre": "FnValue", "span": {"start": {"line": 2}}}}, "summary": "CaughtMutant"}]}'  # noqa: E501
            (self.project / ".gauntlet-out" / "mutants-outcomes.json").write_text(report)
        return ExecResult(0, "", "")


def test_run_checks_rust_coverage_from_absolute_container_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = project(tmp_path, 'language = "rust"\n')
    (root / "src").mkdir()
    (root / "src" / "lib.rs").write_text("pub fn f(x: i32) -> i32 {\n    x + 1\n}\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: RustSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root)]) == 0
    out = capsys.readouterr().out
    assert "produced lcov.info, mutants-outcomes.json" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "mutation score 100.0% >= 90%" in out
    assert "SKIPPED" not in out


# ---- JavaScript: coverage gates and Stryker harden
JS_SOURCE = "function f(x) {\n  return x + 1;\n}\nmodule.exports = { f };\n"


class JsSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if "c8@10.1.3" in argv:
            (self.project / ".gauntlet-out" / "lcov.info").write_text("SF:index.js\nDA:1,1\nDA:2,1\nend_of_record\n")
        if "run" in argv:  # the stubbed Stryker run
            muts = [{"mutatorName": "ArithmeticOperator", "status": s, "location": {"start": {"line": 2}}}
                    for s in ("Killed", "Survived")]  # fmt: skip
            report = json.dumps({"files": {"index.js": {"mutants": muts}}})
            (self.project / ".gauntlet-out" / "stryker.json").write_text(report)
        return ExecResult(0, "", "")


def committed_js_project(root: Path, toml: str = 'language = "javascript"\n') -> Path:
    project(root, toml)
    (root / "index.js").write_text(JS_SOURCE)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    return root


def test_run_checks_javascript_coverage_and_scores_the_stryker_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_js_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: JsSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root)]) == 1
    out = capsys.readouterr().out
    assert "produced lcov.info, stryker.json" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "mutation score 50.0% < 90%" in out
    assert "index.js:2: ArithmeticOperator Survived" in out
    assert "SKIPPED" not in out


def test_harden_asked_for_directly_is_an_error_where_no_tool_is_wired(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    assert cli_run("harden", project(tmp_path, 'language = "dart"\n')) == 2
    assert "harden is not available for dart yet" in capsys.readouterr().err


def test_arch_with_layers_is_an_error_where_no_import_reader_exists(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    root = project(tmp_path, 'language = "javascript"\n[layers]\norder = ["a", "b"]\n')
    assert cli_run("arch", root) == 2
    assert "arch has no import reader for javascript yet" in capsys.readouterr().err


# ---- C#: coverage gates and Stryker.NET mutation
CS_SOURCE = "namespace Demo;\npublic static class A\n{\n    public static int F(int x)\n    {\n        return x + 1;\n    }\n}\n"
CS_COBERTURA = (
    "<coverage><sources><source>/</source></sources>"  # as coverlet writes it in the container
    '<packages><package><classes><class filename="project/src/A.cs"><lines>'
    '<line number="6" hits="1"/></lines></class></classes></package></packages></coverage>'
)


CS_STRYKER = json.dumps(
    {
        "files": {
            "/project/src/A.cs": {
                "mutants": [{"mutatorName": "Math", "status": "Killed", "location": {"start": {"line": 6}}}]
            }
        }
    }
)


class CsSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if argv[0] == "sh" and argv[3:] == ("sh", "/project/.gauntlet-out"):  # moves the report out of results/<guid>/
            (self.project / ".gauntlet-out" / "coverage.cobertura.xml").write_text(CS_COBERTURA)
        if argv[0] == "cp":
            (self.project / ".gauntlet-out" / "stryker-report.json").write_text(CS_STRYKER)
        return ExecResult(0, "", "")


def test_run_checks_csharp_coverage_and_runs_harden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root = project(tmp_path, 'language = "csharp"\n')
    (root / "src").mkdir()
    (root / "src" / "A.cs").write_text(CS_SOURCE)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: CsSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root), "--policy", str(write_policy(""))]) == 0
    out = capsys.readouterr().out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "produced coverage.cobertura.xml, stryker-report.json" in out
    assert "mutation score 100.0% >=" in out


# ---- Java: JaCoCo XML and PIT
JAVA_SOURCE = "package com.x;\npublic class A {\n  int f(int x) {\n    return x + 1;\n  }\n}\n"
JACOCO_XML = (
    '<report name="r"><package name="com/x"><sourcefile name="A.java">'
    '<line nr="4" mi="0" ci="1" mb="0" cb="0"/></sourcefile></package></report>'
)


PIT_REPORT = (Path(__file__).parent / "fixtures" / "pit-mutations.xml").read_text()


class JavaSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if argv[:2] == ("cp", "target/site/jacoco/jacoco.xml"):
            (self.project / ".gauntlet-out" / "jacoco.xml").write_text(JACOCO_XML)
        if argv[:2] == ("cp", "target/pit-reports/mutations.xml"):
            (self.project / ".gauntlet-out" / "mutations.xml").write_text(PIT_REPORT)
        return ExecResult(0, "", "")


def test_run_checks_java_coverage_and_scores_pit_mutants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root = project(tmp_path, 'language = "java"\n')
    (root / "src/main/java/com/x").mkdir(parents=True)
    (root / "src/main/java/com/x/A.java").write_text(JAVA_SOURCE)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: JavaSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root), "--policy", str(write_policy(""))]) == 1
    out = capsys.readouterr().out
    assert "produced jacoco.xml, mutations.xml" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "mutation score 15.4% < 90%" in out
    assert "src/main/java/com/x/A.java:4: ConditionalsBoundaryMutator in f: SURVIVED" in out
    assert "SKIPPED" not in out


# ---- C and C++: coverage gates and universalmutator harden
class CppSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        out = self.project / ".gauntlet-out"
        if "gcovr" in argv:
            (out / "lcov.info").write_text("SF:/project/a.c\nDA:1,1\nDA:2,1\nend_of_record\n")
        if "-P" in argv and argv[2].endswith("cppmutants.py"):  # the stubbed universalmutator run
            muts = [
                {"file": "a.c", "line": 2, "mutation": "x + 1 -> x - 1", "status": s} for s in ("killed", "survived")
            ]
            (out / "cpp-mutants.json").write_text(json.dumps({"mutants": muts}))
        return ExecResult(0, "", "")


def test_run_checks_cpp_coverage_and_scores_the_universalmutator_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    project(tmp_path, 'language = "cpp"\n')
    (tmp_path / "a.c").write_text("int f(int x) {\n  return x + 1;\n}\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "x", "--no-gpg-sign")):
        git(tmp_path, *args)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: CppSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "produced cpp-mutants.json, lcov.info" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "mutation score 50.0% < 90%" in out
    assert "a.c:2: x + 1 -> x - 1: survived" in out
    assert "SKIPPED" not in out


# ---- cpp-clang: clang coverage and a Mull report
class ClangSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        out = self.project / ".gauntlet-out"
        if "coverage" in argv:
            (out / "lcov.info").write_text("SF:/project/a.c\nDA:1,1\nDA:2,1\nend_of_record\n")
        if "mutate" in argv:  # the stubbed Mull run
            muts = [{"mutatorName": "cxx_add_to_sub", "status": s, "location": {"start": {"line": 2}}}
                    for s in ("Killed", "Survived")]  # fmt: skip
            (out / "mull-report.json").write_text(json.dumps({"files": {"/project/a.c": {"mutants": muts}}}))
        return ExecResult(0, "", "")


def test_run_checks_cpp_clang_coverage_and_scores_the_mull_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    project(tmp_path, 'language = "cpp-clang"\n')
    (tmp_path / "a.c").write_text("int f(int x) {\n  return x + 1;\n}\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "x", "--no-gpg-sign")):
        git(tmp_path, *args)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: ClangSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "produced lcov.info, mull-report.json" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "mutation score 50.0% < 90%" in out
    assert "a.c:2: cxx_add_to_sub Survived" in out
    assert "SKIPPED" not in out


# ---- Dart: the same, with the unreadable-file rule visible end to end
DART_SOURCE = "int f(int x) {\n  return x + 1;\n}\n"


class DartSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if "coverage:format_coverage" in argv:
            text = "SF:/project/lib/a.dart\nDA:1,1\nDA:2,1\nend_of_record\n"
            (self.project / ".gauntlet-out" / "lcov.info").write_text(text)
        return ExecResult(0, "", "")


def test_run_checks_dart_coverage_and_names_code_the_reader_could_not_see(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = project(tmp_path, 'language = "dart"\n')
    (root / "lib").mkdir()
    (root / "lib" / "a.dart").write_text(DART_SOURCE)
    (root / "lib" / "b.dart").write_text("int one() => 1;\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "x", "--no-gpg-sign")):
        git(root, *args)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: DartSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root)]) == 1
    out = capsys.readouterr().out
    assert "produced lcov.info" in out
    assert "lib/b.dart:1: (unread code) CRAP inf > 8 (complexity 0, coverage 0%)" in out
    assert "harden: SKIPPED, no mutation tool is wired for dart yet" in out
