import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from helpers import git

from gauntlet import runner
from gauntlet.config import Config
from gauntlet.provenance import MANIFEST, verify
from gauntlet.sandbox import ExecResult
from gauntlet.scope import parse


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.py").write_text("x = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init", "--no-gpg-sign")
    return root


Behave = Callable[[Sequence[str], Path], ExecResult]


class FakeSandbox:
    """Pretends to run steps: `outputs` maps a step's first distinctive argv element to (code, stdout, files)."""

    def __init__(self, project: Path, behave: Behave) -> None:
        self.project, self.behave = project, behave
        self.project_dir = f"{project}/inner"  # as the commands see it, which need not be where the host keeps it
        self.fetched: list[str] = []
        self.calls: list[tuple[list[str], dict[str, str | None], int]] = []
        self.ensured = self.removed = False

    def ensure(self) -> None:
        self.ensured = True

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        self.calls.append((list(argv), dict(env or {}), timeout))
        return self.behave(list(argv), self.project)

    def fetch(self, subdir: str) -> None:
        self.fetched.append(subdir)

    def remove(self) -> None:
        self.removed = True


def python_behaviour(argv: Sequence[str], project: Path) -> ExecResult:
    out = project / runner.OUT_DIR
    if "fake-test" in argv:
        (out / "coverage.json").write_text(json.dumps({"files": {}}))
    if "fake-results" in argv:
        return ExecResult(0, "p.x_a__mutmut_1: killed\n", "")
    return ExecResult(0, "", "")


def make(
    behave: Callable[[Sequence[str], Path], ExecResult],
) -> tuple[Callable[[Path], FakeSandbox], list[FakeSandbox]]:
    made: list[FakeSandbox] = []

    def factory(project: Path) -> FakeSandbox:
        made.append(FakeSandbox(project, behave))
        return made[-1]

    return factory, made


@pytest.mark.parametrize("src", ["../x", "/abs", "a b", "a;b", "$(x)", "-rf"])
def test_the_src_must_be_a_safe_relative_path(src: str) -> None:
    with pytest.raises(ValueError, match="unsafe path"):
        runner.steps(Config(language="fake", src=src), "/p")


def test_the_plan_is_built_for_the_configured_mutation_tool() -> None:
    plan = runner.steps(Config(language="fake", mutation_tool="other"), "/p")
    assert [s.argv for s in plan if s.name == "mutation"] == [("fake-mutate", "other")]


def test_without_a_scope_the_plan_covers_every_file(repo: Path) -> None:
    assert runner.in_scope(repo, Config(language="fake"), parse([])) == ()
    plan = runner.steps(Config(language="fake"), "/p")
    assert [s.argv for s in plan if s.name == "mutation"] == [("fake-mutate", "mutmut")]


def test_a_scope_names_the_source_files_the_mutation_step_looks_at(repo: Path, tmp_path: Path) -> None:
    for name in ("b.py", "tests/test_a.py", "conftest.py", "notes.txt"):
        (repo / name).parent.mkdir(exist_ok=True)
        (repo / name).write_text("x = 1\n")
    cfg = Config(language="fake")
    scope = parse(["a.py:1-1", "tests/", "conftest.py", "notes.txt", "gone.py"])
    assert runner.in_scope(repo, cfg, scope) == ("a.py",)  # never a test, never a file that is no source
    factory, made = make(python_behaviour)
    runner.produce(repo, cfg, tmp_path / "out", factory, scope)
    assert [argv for argv, _, _ in made[0].calls if argv[0] == "fake-mutate"] == [["fake-mutate", "mutmut", "a.py"]]


@pytest.mark.parametrize("only", ["tests/", "notes.txt", "gone.py"])
def test_a_scope_with_no_source_outside_the_tests_stops_before_anything_runs(
    repo: Path, tmp_path: Path, only: str
) -> None:
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("x = 1\n")
    (repo / "notes.txt").write_text("x\n")
    factory, made = make(python_behaviour)
    with pytest.raises(ValueError, match="^nothing to check: the scope touches no source file outside the tests$"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory, parse([only]))
    assert made == []


def test_each_step_is_announced_before_it_runs(repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    factory, _ = make(python_behaviour)
    runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    captured = capsys.readouterr()
    assert captured.err == (
        "gauntlet: tests (up to 60 min)\ngauntlet: mutation (up to 120 min)\ngauntlet: mutation-results (up to 30 min)\n"
    )
    assert captured.out == ""


def test_produce_runs_in_a_snapshot_copies_artifacts_and_stamps(repo: Path, tmp_path: Path) -> None:
    factory, made = make(python_behaviour)
    out = tmp_path / "out"
    names = runner.produce(repo, Config(language="fake"), out, factory)
    assert names == ["coverage.json", "mutmut-results.txt"]
    (box,) = made
    assert box.ensured and box.removed
    assert box.fetched == [runner.OUT_DIR]  # results are brought back from the sandbox before it goes
    assert box.project != repo
    assert box.calls[0][0][:2] == ["fake-test", "."]
    assert (out / "mutmut-results.txt").read_text() == "p.x_a__mutmut_1: killed\n"
    assert (out / MANIFEST).exists()
    verify(out, repo, names)


def test_the_sandbox_is_always_removed(repo: Path, tmp_path: Path) -> None:
    def boom(argv: Sequence[str], project: Path) -> ExecResult:
        return ExecResult(1, "", "tests failed")

    factory, made = make(boom)
    with pytest.raises(ValueError, match=r"step 'tests' failed \(exit 1\)"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    assert made[0].removed


def test_mutation_may_fail_but_tests_may_not(repo: Path, tmp_path: Path) -> None:
    def flaky(argv: Sequence[str], project: Path) -> ExecResult:
        if "fake-mutate" in argv:
            return ExecResult(1, "", "survivors found")
        return python_behaviour(argv, project)

    factory, _ = make(flaky)
    assert runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_missing_required_artifacts_are_an_error(repo: Path, tmp_path: Path) -> None:
    factory, _ = make(lambda argv, project: ExecResult(0, "", ""))
    with pytest.raises(ValueError, match="did not produce coverage.json"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_a_source_change_during_the_run_invalidates_it(repo: Path, tmp_path: Path) -> None:
    def meddle(argv: Sequence[str], project: Path) -> ExecResult:
        (repo / "a.py").write_text("x = 2\n")
        return python_behaviour(argv, project)

    factory, _ = make(meddle)
    with pytest.raises(ValueError, match="source changed while the gauntlet ran"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    assert not (tmp_path / "out" / MANIFEST).exists()


def test_planted_symlinks_and_oversized_artifacts_are_refused(repo: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("secret")

    def plant(argv: Sequence[str], project: Path) -> ExecResult:
        out = project / runner.OUT_DIR
        if "fake-test" in argv:
            (out / "coverage.json").symlink_to(secret)
        return ExecResult(0, "p.x: killed\n", "")

    factory, _ = make(plant)
    with pytest.raises(ValueError, match="coverage.json is a symlink"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_oversized_artifacts_are_refused(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "MAX_ARTIFACT_BYTES", 5)
    factory, _ = make(python_behaviour)
    with pytest.raises(ValueError, match="over the 5 byte limit"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_a_file_the_tests_leave_never_stands_in_for_a_captured_artifact(repo: Path, tmp_path: Path) -> None:
    def forge(argv: Sequence[str], project: Path) -> ExecResult:
        if "fake-test" in argv:
            (project / runner.OUT_DIR / "mutmut-results.txt").write_text("p.x: killed\n")
        return python_behaviour(argv, project) if "fake-test" in argv else ExecResult(0, "", "")

    factory, _ = make(forge)
    with pytest.raises(ValueError, match=r"^the sandbox did not produce mutmut-results\.txt$"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_the_snapshot_directory_is_cleaned_up(repo: Path, tmp_path: Path) -> None:
    factory, made = make(python_behaviour)
    runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    assert not made[0].project.exists()


def test_oversized_captured_output_is_refused(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner, "MAX_ARTIFACT_BYTES", 20
    )  # coverage.json (13 bytes) fits, the mutmut output (24) does not
    factory, _ = make(python_behaviour)
    with pytest.raises(ValueError, match=r"mutmut-results.txt is 24 bytes, over the 20 byte limit"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_the_snapshot_lives_in_a_private_temp_directory(repo: Path, tmp_path: Path) -> None:
    factory, made = make(python_behaviour)
    runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    project = made[0].project
    assert project.name == "project"
    assert project.parent.name.startswith("gauntlet-")


def test_failed_step_message_uses_stderr_then_stdout_and_keeps_the_tail(repo: Path, tmp_path: Path) -> None:
    def boom(stdout: str, stderr: str) -> Behave:
        return lambda argv, project: ExecResult(3, stdout, stderr)

    for stdout, stderr, expected in [("out only", "", "out only"), ("also", "err", "err \\| also")]:
        factory, _ = make(boom(stdout, stderr))
        with pytest.raises(ValueError, match=rf"^step 'tests' failed \(exit 3\): {expected}$"):
            runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    factory, _ = make(boom("", "A" * 1500 + "B" * 2000))
    with pytest.raises(ValueError, match="B{2000}$") as e:
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    assert "A" not in str(e.value).split(": ", 1)[1]


def test_the_source_changed_message_is_exact(repo: Path, tmp_path: Path) -> None:
    def meddle(argv: Sequence[str], project: Path) -> ExecResult:
        (repo / "a.py").write_text("x = 3\n")
        return python_behaviour(argv, project)

    factory, _ = make(meddle)
    with pytest.raises(ValueError, match=r"^source changed while the gauntlet ran; rerun it$"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_a_step_that_prints_nothing_stores_nothing(repo: Path, tmp_path: Path) -> None:
    def quiet(argv: Sequence[str], project: Path) -> ExecResult:
        if "fake-test" in argv:
            (project / runner.OUT_DIR / "coverage.json").write_text("{}")
        return ExecResult(0, "", "")

    factory, _ = make(quiet)
    with pytest.raises(ValueError, match=r"^the sandbox did not produce mutmut-results\.txt$"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    assert not (tmp_path / "out" / "mutmut-results.txt").exists()


def test_a_step_with_output_but_no_capture_name_stores_nothing(repo: Path, tmp_path: Path) -> None:
    noisy, _ = make(lambda argv, project: python_behaviour(argv, project))
    names = runner.produce(repo, Config(language="fake"), tmp_path / "out", noisy)
    assert names == ["coverage.json", "mutmut-results.txt"]
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["coverage.json", MANIFEST, "mutmut-results.txt"]


def test_the_stale_report_is_removed_by_the_sandbox_right_before_the_mutation_step(repo: Path, tmp_path: Path) -> None:
    factory, made = make(python_behaviour)
    runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    calls = made[0].calls
    removal = next(i for i, c in enumerate(calls) if c[0][0] == "rm")
    assert calls[removal][0][-1] == f"{made[0].project}/inner/.gauntlet-out/mutmut-results.txt"
    assert calls[removal + 1][0] == ["fake-mutate", "mutmut"]  # the mutation run follows at once
    assert calls[removal][1:] == ({}, 60) and calls[removal][0][:2] == ["rm", "-rf"]


def test_a_failed_report_removal_stops_the_run(repo: Path, tmp_path: Path) -> None:
    factory, _ = make(lambda argv, project: ExecResult(1 if argv[0] == "rm" else 0, "", "read-only file system"))
    with pytest.raises(ValueError, match="could not clear the old mutation report: read-only file system"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_a_symlinked_output_directory_is_refused_before_anything_is_read(repo: Path, tmp_path: Path) -> None:
    host = tmp_path / "host"
    host.mkdir()
    (host / "coverage.json").write_text('{"files": {}}')

    def behave(argv: Sequence[str], project: Path) -> ExecResult:
        if "fake-test" in argv:  # the tests replace .gauntlet-out with a link to a host directory
            shutil.rmtree(project / runner.OUT_DIR)
            (project / runner.OUT_DIR).symlink_to(host)
        return ExecResult(0, "", "")

    factory, _ = make(behave)
    with pytest.raises(ValueError, match=r"\.gauntlet-out is a symlink"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)


def test_a_sandbox_that_fails_to_start_is_still_removed(repo: Path, tmp_path: Path) -> None:
    class Broken(FakeSandbox):
        def ensure(self) -> None:
            raise ValueError("cannot start")

    made: list[Broken] = []

    def factory(project: Path) -> Broken:
        made.append(Broken(project, python_behaviour))
        return made[-1]

    with pytest.raises(ValueError, match="cannot start"):
        runner.produce(repo, Config(language="fake"), tmp_path / "out", factory)
    assert made[0].removed and not made[0].calls
