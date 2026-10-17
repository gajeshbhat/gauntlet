"""The helper that runs inside the sandbox for cpp-clang. Its subprocess calls are faked; its logic is real."""

import hashlib
import json
import subprocess
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def driver() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "driver"}
    exec((files("gauntlet") / "data" / "cpp-clang-driver.txt").read_text(), namespace)  # noqa: S102
    return namespace


class Calls:
    """Stands in for subprocess.run: records every command and answers `ctest` with a fixed test list."""

    def __init__(self, tests: list[dict[str, Any]], reports: dict[str, Any] | None = None) -> None:
        self.argvs: list[list[str]] = []
        self.tests, self.reports = tests, reports or {}

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.argvs.append(list(argv))
        if argv[0] == "ctest":
            return subprocess.CompletedProcess(argv, 0, json.dumps({"tests": self.tests}).encode())
        if "--report-dir" in argv:
            where = Path(argv[argv.index("--report-dir") + 1])
            where.mkdir(parents=True)
            (where / "r.json").write_text(json.dumps(self.reports[argv[1]]))
        if "stdout" in kwargs:
            kwargs["stdout"].write(b"SF:/project/a.c\n")
        return subprocess.CompletedProcess(argv, 0)


def fake(monkeypatch: pytest.MonkeyPatch, calls: Calls) -> None:
    monkeypatch.setattr(subprocess, "run", calls)


def test_only_executables_built_in_the_build_directory_are_test_commands(
    driver: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = tmp_path / "build"
    build.mkdir()
    tests = [
        {"command": [str(build / "t"), "--fast"]},
        {"command": [str(build / "t"), "--fast"]},  # the same command twice counts once
        {"command": ["/usr/bin/python3", "check.py"]},  # not ours: left alone
        {"command": [str(tmp_path / "build-evil" / "t")]},  # a sibling directory is not the build directory
        {"name": "no command"},
    ]
    fake(monkeypatch, Calls(tests))
    assert driver["tests"](str(build)) == [(str(build / "t"), "--fast")]


def test_a_project_with_no_test_executable_is_an_error(
    driver: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake(monkeypatch, Calls([]))
    with pytest.raises(SystemExit, match="ctest lists no test executable"):
        driver["tests"](str(tmp_path))


def test_install_checks_the_hash_before_unpacking(
    driver: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "mull.deb"
    package.write_bytes(b"deb")
    calls = Calls([])
    fake(monkeypatch, calls)
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        driver["install"](package.as_uri(), "0" * 64, str(tmp_path / "bad"))
    assert calls.argvs == []  # nothing was unpacked
    driver["install"](package.as_uri(), hashlib.sha256(b"deb").hexdigest(), str(tmp_path / "ok"))
    assert calls.argvs == [["dpkg-deb", "-x", str(tmp_path / "ok" / "mull.deb"), str(tmp_path / "ok")]]


def test_coverage_merges_the_profiles_and_exports_lcov_for_every_test_executable(
    driver: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build, profiles = tmp_path / "build", tmp_path / "prof"
    profiles.mkdir()
    (profiles / "2.profraw").write_text("")
    (profiles / "1.profraw").write_text("")
    calls = Calls([{"command": [str(build / "a")]}, {"command": [str(build / "b")]}])
    fake(monkeypatch, calls)
    out = tmp_path / "lcov.info"
    driver["coverage"](str(build), str(profiles), str(out))
    merge, export = calls.argvs[0], calls.argvs[2]
    assert merge == [
        "llvm-profdata", "merge", "-sparse", str(profiles / "1.profraw"), str(profiles / "2.profraw"),
        "-o", str(profiles / "merged.profdata"),
    ]  # fmt: skip
    assert export[:3] == ["llvm-cov", "export", "-format=lcov"] and "-ignore-filename-regex" in export[4]
    assert export[5:] == ["-object", str(build / "a"), "-object", str(build / "b")]
    assert out.read_text() == "SF:/project/a.c\n"


def test_coverage_without_profile_data_is_an_error(driver: dict[str, Any], tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no profile data"):
        driver["coverage"](str(tmp_path), str(tmp_path), str(tmp_path / "lcov.info"))


def _mutant(mutant_id: str, status: str) -> dict[str, Any]:
    return {"id": mutant_id, "status": status}


def test_a_mutant_is_caught_when_any_test_executable_caught_it(driver: dict[str, Any]) -> None:
    first = {"files": {"a.c": {"language": "cpp", "mutants": [_mutant("x", "Survived"), _mutant("y", "Killed")]}}}
    second = {"files": {"a.c": {"language": "cpp", "mutants": [_mutant("x", "Killed"), _mutant("y", "Survived")]}}}
    third = {"files": {"b.c": {"language": "cpp", "mutants": [_mutant("z", "Survived")]}}}
    merged = driver["merge"]([first, second, third])
    assert merged["files"]["a.c"]["mutants"] == [_mutant("x", "Killed"), _mutant("y", "Killed")]
    assert merged["files"]["b.c"]["mutants"] == [_mutant("z", "Survived")]


def test_mutate_runs_mull_on_each_test_command_and_writes_one_merged_report(
    driver: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = tmp_path / "build"
    a, b = str(build / "a"), str(build / "b")
    one = {"files": {"a.c": {"language": "cpp", "mutants": [_mutant("x", "Survived")]}}}
    two = {"files": {"a.c": {"language": "cpp", "mutants": [_mutant("x", "Killed")]}}}
    calls = Calls([{"command": [a, "--flag"]}, {"command": [b]}], {a: one, b: two})
    fake(monkeypatch, calls)
    out = tmp_path / "mull-report.json"
    driver["mutate"](str(build), "mull-runner", str(tmp_path / "reports"), str(out))
    first = calls.argvs[1]
    assert first[:2] == ["mull-runner", a] and first[-3:] == ["--allow-surviving", "--", "--flag"]
    assert first[2:6] == ["--reporters", "Elements", "--report-dir", str(tmp_path / "reports" / "0")]
    assert json.loads(out.read_text())["files"]["a.c"]["mutants"] == [_mutant("x", "Killed")]
