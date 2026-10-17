import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from gauntlet import runner
from gauntlet.config import Config
from gauntlet.provenance import MANIFEST, verify
from gauntlet.sandbox import ExecResult

GITENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env={**os.environ, **GITENV})


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
        self.calls: list[tuple[list[str], dict[str, str | None], int]] = []
        self.ensured = self.removed = False

    def ensure(self) -> None:
        self.ensured = True

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        self.calls.append((list(argv), dict(env or {}), timeout))
        return self.behave(list(argv), self.project)

    def remove(self) -> None:
        self.removed = True


def python_behaviour(argv: Sequence[str], project: Path) -> ExecResult:
    out = project / runner.OUT_DIR
    if "pytest" in argv:
        (out / "coverage.json").write_text(json.dumps({"files": {}}))
    if argv[-3:] == ["results", "--all", "true"]:
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


def test_python_steps_are_fixed_commands_with_pinned_tools() -> None:
    steps = runner.steps(Config(language="python", src="src"), Path("/unused"))
    assert [s.name for s in steps] == ["tests", "mutation", "mutation-results"]
    assert steps[0].argv == (
        "uv",
        "run",
        "--project",
        "/project",
        "--with",
        "pytest-cov==7.1.0",
        "pytest",
        "-q",
        "--cov=src",
        "--cov-branch",
        "--cov-report=json:/project/.gauntlet-out/coverage.json",
    )
    assert steps[1].argv[:6] == ("uv", "run", "--project", "/project", "--with", "mutmut==3.8.0")
    assert steps[1].must_pass is False
    assert steps[2].capture == "mutmut-results.txt"


def test_go_steps(tmp_path: Path) -> None:
    (tmp_path / "lxd" / "device").mkdir(parents=True)
    for name in ("disk.go", "nic.go"):
        (tmp_path / "lxd" / "device" / name).write_text("package device\n")
    cfg = Config(language="go", packages=("./lxd/device/",), mutation_dir="lxd/device", mutate_only=("disk.go",))
    steps = {s.name: s for s in runner.steps(cfg, tmp_path)}
    assert steps["install-gremlins"].argv == ("go", "install", "github.com/go-gremlins/gremlins/cmd/gremlins@v0.6.0")
    assert steps["tests"].argv[:4] == ("go", "test", "-count=1", "-coverprofile=/project/.gauntlet-out/cover.out")
    assert steps["tests"].argv[-1] == "./lxd/device/"
    assert steps["imports"].argv[-1] == "./lxd/device/"
    mutation = steps["mutation"].argv
    assert mutation[:2] == ("/project/.gauntlet-out/bin/gremlins", "unleash")
    assert mutation[2:4] == ("-E", "^nic\\.go$")
    assert mutation[-3:] == ("-o", "/project/.gauntlet-out/mutation.json", "lxd/device")
    assert steps["mutation"].must_pass is False
    assert dict(steps["tests"].env) == {"GOBIN": "/project/.gauntlet-out/bin", "GOFLAGS": "-buildvcs=false"}


def test_javascript_steps(tmp_path: Path) -> None:
    install, tests, *_ = runner.steps(Config(language="javascript"), tmp_path)
    assert install.argv == ("npm", "ci", "--ignore-scripts")
    assert tests.argv == (
        "npx", "--yes", "c8@10.1.3", "--reporter=lcovonly", "--reports-dir=/project/.gauntlet-out", "npm", "test"
    )  # fmt: skip
    assert tests.timeout == 3600


def test_javascript_mutation_steps_are_fixed_pinned_and_use_our_own_stryker_config(tmp_path: Path) -> None:
    steps = {s.name: s for s in runner.steps(Config(language="javascript"), tmp_path)}
    assert steps["install-stryker"].argv == (
        "npm", "install", "--prefix", "/project/.gauntlet-out/stryker", "--ignore-scripts", "--no-audit", "--no-fund",
        "--no-save", "@stryker-mutator/core@9.6.1",
    )  # fmt: skip
    write = steps["stryker-config"].argv
    assert write[:4] == ("sh", "-c", 'printf %s "$1" > "$2"', "sh")  # a fixed script; the config is data
    assert write[-1] == "/project/.gauntlet-out/stryker.conf.json"
    config = json.loads(write[4])
    assert config["mutate"] == [
        "**/*.{js,mjs,cjs,jsx,ts,tsx}", "!**/node_modules/**", "!.gauntlet-out/**", "!tests/**", "!test/**",
        "!__tests__/**",
    ]  # fmt: skip
    assert config["jsonReporter"] == {"fileName": "/project/.gauntlet-out/stryker.json"}
    assert config["commandRunner"] == {"command": "npm test"}
    mutation = steps["mutation"]
    assert mutation.argv == (
        "node",
        "/project/.gauntlet-out/stryker/node_modules/.bin/stryker",
        "run",
        "/project/.gauntlet-out/stryker.conf.json",
    )  # an explicit config path: a repo's stryker.conf.* is never read
    assert (mutation.timeout, mutation.must_pass) == (7200, False)
    assert runner.REQUIRED["javascript"] == ("lcov.info", "stryker.json")


def test_csharp_steps(tmp_path: Path) -> None:
    tests, report, *_ = runner.steps(Config(language="csharp"), tmp_path)
    assert tests.argv == (
        "dotnet", "test", "--collect", "XPlat Code Coverage",
        "--results-directory", "/project/.gauntlet-out/results", "-p:RunSettingsFilePath=",
    )  # fmt: skip  # an empty RunSettingsFilePath: a repo's own .runsettings cannot add exclusions
    assert tests.timeout == 3600
    assert dict(tests.env) == {"XDG_RUNTIME_DIR": "/tmp", "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    assert report.argv[:2] == ("sh", "-c") and report.argv[3:] == ("sh", "/project/.gauntlet-out")
    assert report.argv[2] == runner.COPY_REPORT


def test_csharp_mutation_steps_pin_the_tool_and_use_only_our_config(tmp_path: Path) -> None:
    *_, install, config, mutation, collect = runner.steps(Config(language="csharp"), tmp_path)
    out = "/project/.gauntlet-out"
    assert install.argv == (
        "dotnet",
        "tool",
        "install",
        "--tool-path",
        f"{out}/tools",
        "dotnet-stryker",
        "--version",
        "4.8.1",
    )
    assert config.argv[2] == 'echo \'{"stryker-config":{}}\' > "$1"'  # empty: nothing ignored, nothing narrowed
    assert config.argv[:2] == ("sh", "-c") and config.argv[3:] == ("sh", f"{out}/stryker-config.json")
    assert mutation.argv == (
        f"{out}/tools/dotnet-stryker", "--config-file", f"{out}/stryker-config.json", "--mutate", "**/*.cs",
        "--reporter", "json", "--output", f"{out}/stryker",
    )  # fmt: skip
    assert (mutation.must_pass, mutation.timeout) == (False, 7200)
    assert dict(mutation.env) == dict(install.env) and "XDG_RUNTIME_DIR" in dict(install.env)
    assert collect.argv == ("cp", f"{out}/stryker/reports/mutation-report.json", f"{out}/stryker-report.json")
    assert collect.must_pass is False
    assert "stryker-report.json" in runner.REQUIRED["csharp"] + runner.FILES["csharp"]


def test_java_steps(tmp_path: Path) -> None:
    tests, collect, fetch, mutation, report = runner.steps(Config(language="java"), tmp_path)
    jacoco = "org.jacoco:jacoco-maven-plugin:0.8.12"
    m2 = "-Dmaven.repo.local=/project/.gauntlet-out/m2"
    assert tests.argv == ("mvn", "-B", "-ntp", m2, f"{jacoco}:prepare-agent", "test", f"{jacoco}:report")
    assert tests.timeout == 3600
    assert collect.argv == ("cp", "target/site/jacoco/jacoco.xml", "/project/.gauntlet-out/jacoco.xml")
    assert fetch.argv == (
        "mvn", "-B", "-ntp", m2, "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get",
        "-Dartifact=org.pitest:pitest-junit5-plugin:1.2.1", "-Dtransitive=false",
    )  # fmt: skip
    assert mutation.argv[:5] == ("mvn", "-B", "-ntp", m2, "org.pitest:pitest-maven:1.17.4:mutationCoverage")
    assert set(mutation.argv[5:]) == {
        "-DoutputFormats=XML", "-DtimestampedReports=false", "-Dmutators=DEFAULTS",
        "-DadditionalClasspathElements=/project/.gauntlet-out/m2/org/pitest/pitest-junit5-plugin/1.2.1/"
        "pitest-junit5-plugin-1.2.1.jar",
        "-DexcludedClasses=", "-DexcludedMethods=", "-DexcludedTestClasses=", "-DwithHistory=false", "-DavoidCallsTo=",
    }  # fmt: skip  # explicit, gauntlet-owned values; no -DtargetClasses (PIT then takes the built packages)
    assert (mutation.timeout, mutation.must_pass) == (7200, False)
    assert report.argv == ("cp", "target/pit-reports/mutations.xml", "/project/.gauntlet-out/mutations.xml")
    assert report.must_pass is False


def test_rust_steps(tmp_path: Path) -> None:
    rustup, install, tests, *extra = runner.steps(Config(language="rust"), tmp_path)
    assert rustup.argv == ("rustup", "component", "add", "llvm-tools-preview")
    assert install.argv == (
        "cargo", "install", "--locked", "--version", "0.6.21", "cargo-llvm-cov", "--root", "/project/.gauntlet-out/cargo"
    )  # fmt: skip
    assert tests.argv == (
        "/project/.gauntlet-out/cargo/bin/cargo-llvm-cov", "llvm-cov", "--locked", "--lcov",
        "--output-path", "/project/.gauntlet-out/lcov.info",
    )  # fmt: skip
    assert tests.timeout == 3600
    get, mutation, report = extra
    assert get.argv == (
        "cargo", "install", "--locked", "--version", "27.1.0", "cargo-mutants", "--root", "/project/.gauntlet-out/cargo"
    )  # fmt: skip
    assert mutation.argv == (
        "/project/.gauntlet-out/cargo/bin/cargo-mutants", "mutants", "--no-config",
        "--output", "/project/.gauntlet-out/mutants",
    )  # fmt: skip
    assert (mutation.timeout, mutation.must_pass, report.must_pass) == (7200, False, False)
    assert report.argv[0] == "cp" and report.argv[2] == "/project/.gauntlet-out/mutants-outcomes.json"
    assert "mutants-outcomes.json" in runner.REQUIRED["rust"] and "mutants-outcomes.json" in runner.FILES["rust"]


@pytest.mark.parametrize("src", ["../x", "/abs", "a b", "a;b", "$(x)", "-rf"])
def test_python_src_must_be_a_safe_relative_path(src: str) -> None:
    with pytest.raises(ValueError, match="unsafe path"):
        runner.steps(Config(language="python", src=src), Path("/unused"))


@pytest.mark.parametrize("pkg", ["lxd", "../x", "./a b", "./a;b", "-race", "./$(x)"])
def test_go_packages_must_be_safe_patterns(pkg: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe package pattern"):
        runner.steps(Config(language="go", packages=(pkg,)), tmp_path)


def test_produce_runs_in_a_snapshot_copies_artifacts_and_stamps(repo: Path, tmp_path: Path) -> None:
    factory, made = make(python_behaviour)
    out = tmp_path / "out"
    names = runner.produce(repo, Config(language="python"), out, factory)
    assert names == ["coverage.json", "mutmut-results.txt"]
    (box,) = made
    assert box.ensured and box.removed
    assert box.project != repo
    assert box.calls[0][0][4:6] == ["--with", "pytest-cov==7.1.0"]
    assert (out / "mutmut-results.txt").read_text() == "p.x_a__mutmut_1: killed\n"
    assert (out / MANIFEST).exists()
    verify(out, repo, names)


def test_the_sandbox_is_always_removed(repo: Path, tmp_path: Path) -> None:
    def boom(argv: Sequence[str], project: Path) -> ExecResult:
        return ExecResult(1, "", "tests failed")

    factory, made = make(boom)
    with pytest.raises(ValueError, match=r"step 'tests' failed \(exit 1\)"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
    assert made[0].removed


def test_mutation_may_fail_but_tests_may_not(repo: Path, tmp_path: Path) -> None:
    def flaky(argv: Sequence[str], project: Path) -> ExecResult:
        if "run" in argv and "mutmut" in argv and "results" not in argv:
            return ExecResult(1, "", "survivors found")
        return python_behaviour(argv, project)

    factory, _ = make(flaky)
    assert runner.produce(repo, Config(language="python"), tmp_path / "out", factory)


def test_missing_required_artifacts_are_an_error(repo: Path, tmp_path: Path) -> None:
    factory, _ = make(lambda argv, project: ExecResult(0, "", ""))
    with pytest.raises(ValueError, match="did not produce coverage.json"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)


def test_a_source_change_during_the_run_invalidates_it(repo: Path, tmp_path: Path) -> None:
    def meddle(argv: Sequence[str], project: Path) -> ExecResult:
        (repo / "a.py").write_text("x = 2\n")
        return python_behaviour(argv, project)

    factory, _ = make(meddle)
    with pytest.raises(ValueError, match="source changed while the gauntlet ran"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
    assert not (tmp_path / "out" / MANIFEST).exists()


def test_planted_symlinks_and_oversized_artifacts_are_refused(repo: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("secret")

    def plant(argv: Sequence[str], project: Path) -> ExecResult:
        out = project / runner.OUT_DIR
        if "pytest" in argv:
            (out / "coverage.json").symlink_to(secret)
        return ExecResult(0, "p.x: killed\n", "")

    factory, _ = make(plant)
    with pytest.raises(ValueError, match="coverage.json is a symlink"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)


def test_oversized_artifacts_are_refused(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "MAX_ARTIFACT_BYTES", 5)
    factory, _ = make(python_behaviour)
    with pytest.raises(ValueError, match="over the 5 byte limit"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)


def test_go_pipeline_collects_captured_and_written_artifacts(repo: Path, tmp_path: Path) -> None:
    def go_behaviour(argv: Sequence[str], project: Path) -> ExecResult:
        out = project / runner.OUT_DIR
        if argv[:2] == ["go", "test"]:
            (out / "cover.out").write_text("mode: set\n")
        if argv[:2] == [f"{runner.IN_SANDBOX}/bin/gremlins", "unleash"]:
            (out / "mutation.json").write_text('{"files": []}')
        if argv[:2] == ["go", "list"]:
            return ExecResult(0, "m/a fmt\n", "")
        return ExecResult(0, "", "")

    factory, _ = make(go_behaviour)
    names = runner.produce(repo, Config(language="go"), tmp_path / "out", factory)
    assert names == ["cover.out", "imports.txt", "mutation.json"]
    assert (tmp_path / "out" / "imports.txt").read_text() == "m/a fmt\n"


def test_the_snapshot_directory_is_cleaned_up(repo: Path, tmp_path: Path) -> None:
    factory, made = make(python_behaviour)
    runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
    assert not made[0].project.exists()


def test_oversized_captured_output_is_refused(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner, "MAX_ARTIFACT_BYTES", 20
    )  # coverage.json (13 bytes) fits, the mutmut output (24) does not
    factory, _ = make(python_behaviour)
    with pytest.raises(ValueError, match=r"mutmut-results.txt is 24 bytes, over the 20 byte limit"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)


def test_steps_receive_their_timeouts_and_environment(repo: Path, tmp_path: Path) -> None:
    def go_ok(argv: Sequence[str], project: Path) -> ExecResult:
        if argv[:2] == ["go", "test"]:
            (project / runner.OUT_DIR / "cover.out").write_text("mode: set\n")
        if argv[:2] == ["go", "list"]:
            return ExecResult(0, "z\n", "")
        return ExecResult(0, "", "")

    factory, made = make(go_ok)
    runner.produce(repo, Config(language="go"), tmp_path / "out", factory)
    calls = made[0].calls
    assert [(c[0][1] if c[0][0] == "go" else c[0][0].split("/")[-1], c[2]) for c in calls][:3] == [
        ("install", 1800),
        ("test", 3600),
        ("list", 1800),
    ]
    assert calls[0][1] == {"GOBIN": "/project/.gauntlet-out/bin", "GOFLAGS": "-buildvcs=false"}
    assert calls[-1][2] == 7200  # mutation


def test_the_snapshot_lives_in_a_private_temp_directory(repo: Path, tmp_path: Path) -> None:
    factory, made = make(python_behaviour)
    runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
    project = made[0].project
    assert project.name == "project"
    assert project.parent.name.startswith("gauntlet-")


def test_failed_step_message_uses_stderr_then_stdout_and_keeps_the_tail(repo: Path, tmp_path: Path) -> None:
    def boom(stdout: str, stderr: str) -> Behave:
        return lambda argv, project: ExecResult(3, stdout, stderr)

    for stdout, stderr, expected in [("out only", "", "out only"), ("also", "err", "err \\| also")]:
        factory, _ = make(boom(stdout, stderr))
        with pytest.raises(ValueError, match=rf"^step 'tests' failed \(exit 3\): {expected}$"):
            runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
    factory, _ = make(boom("", "A" * 1500 + "B" * 2000))
    with pytest.raises(ValueError, match="B{2000}$") as e:
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
    assert "A" not in str(e.value).split(": ", 1)[1]


def test_the_source_changed_message_is_exact(repo: Path, tmp_path: Path) -> None:
    def meddle(argv: Sequence[str], project: Path) -> ExecResult:
        (repo / "a.py").write_text("x = 3\n")
        return python_behaviour(argv, project)

    factory, _ = make(meddle)
    with pytest.raises(ValueError, match=r"^source changed while the gauntlet ran; rerun it$"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)


def test_a_step_that_prints_nothing_stores_nothing(repo: Path, tmp_path: Path) -> None:
    def quiet(argv: Sequence[str], project: Path) -> ExecResult:
        if "pytest" in argv:
            (project / runner.OUT_DIR / "coverage.json").write_text("{}")
        return ExecResult(0, "", "")

    factory, _ = make(quiet)
    with pytest.raises(ValueError, match=r"^the sandbox did not produce mutmut-results\.txt$"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
    assert not (tmp_path / "out" / "mutmut-results.txt").exists()


def test_a_step_with_output_but_no_capture_name_stores_nothing(repo: Path, tmp_path: Path) -> None:
    noisy, _ = make(lambda argv, project: python_behaviour(argv, project))
    names = runner.produce(repo, Config(language="python"), tmp_path / "out", noisy)
    assert names == ["coverage.json", "mutmut-results.txt"]
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["coverage.json", MANIFEST, "mutmut-results.txt"]


def test_cpp_steps_are_fixed_pinned_and_ignore_the_repos_gcovr_config(tmp_path: Path) -> None:
    install, configure, build, tests, coverage = runner.steps(Config(language="cpp"), tmp_path)
    assert install.argv[:2] == ("sh", "-c")
    assert "sha256sum -c -" in install.argv[2] and runner.PIP_SHA256 in install.argv[2]
    script = install.argv[2]
    assert "--require-hashes" in script and "--no-deps" in script and "python3 -P -m pip" in script
    assert "cmake==4.4.4" in script and "gcovr==8.7" in script and "--hash=sha256:" in script
    assert "--coverage" in " ".join(configure.argv) and configure.argv[0] == "/project/.gauntlet-out/py/bin/cmake"
    assert build.argv[1:] == ("--build", "/project/.gauntlet-out/build")
    assert tests.argv[0] == "/project/.gauntlet-out/py/bin/ctest" and tests.timeout == 3600
    assert coverage.argv[:6] == ("python3", "-P", "-m", "gcovr", "--config", "/project/.gauntlet-out/gcovr.cfg")
    assert coverage.argv[-2:] == ("--lcov", "/project/.gauntlet-out/lcov.info")
    assert dict(coverage.env) == {"PYTHONPATH": "/project/.gauntlet-out/py"}


def test_dart_steps(tmp_path: Path) -> None:
    get, activate, tests, report = runner.steps(Config(language="dart"), tmp_path)
    assert get.argv == ("dart", "pub", "get", "--enforce-lockfile")  # the lockfile decides; nothing is re-resolved
    assert activate.argv == ("dart", "pub", "global", "activate", "coverage", "1.15.0")
    assert tests.argv == ("dart", "test", "--coverage=/project/.gauntlet-out/raw")
    assert tests.timeout == 3600 and report.argv[:5] == ("dart", "pub", "global", "run", "coverage:format_coverage")
    assert report.argv[5:] == (
        "--lcov", "--in=/project/.gauntlet-out/raw", "--out=/project/.gauntlet-out/lcov.info",
        "--report-on=lib", "--report-on=bin", "--packages=.dart_tool/package_config.json",
    )  # fmt: skip
    assert "--check-ignore" not in report.argv  # coverage:ignore comments do not hide code from the gate


def test_the_cpp_lock_pins_every_requirement_with_hashes() -> None:
    from importlib.resources import files

    lock = (files("gauntlet") / "data" / "cpp-requirements.txt").read_text()
    entries = [line for line in lock.splitlines() if line and not line.startswith((" ", "#"))]
    assert entries and all("==" in line for line in entries)
    assert lock.count("--hash=sha256:") >= len(entries)


def test_a_mutation_report_planted_by_the_tests_does_not_survive_a_crashed_mutation_run(
    repo: Path, tmp_path: Path
) -> None:
    def behave(argv: Sequence[str], project: Path) -> ExecResult:
        out = project / runner.OUT_DIR
        if argv[0] == "rm":  # what the sandbox does with the removal step
            (out / Path(argv[-1]).name).unlink(missing_ok=True)
        if "c8@10.1.3" in argv:  # the repo's own tests plant a flattering report
            (out / "lcov.info").write_text("SF:a.js\nDA:1,1\nend_of_record\n")
            (out / "stryker.json").write_text('{"files": {}}')
        return ExecResult(0, "", "")  # the real Stryker run produces nothing

    factory, _ = make(behave)
    with pytest.raises(ValueError, match="the sandbox did not produce stryker.json"):
        runner.produce(repo, Config(language="javascript"), tmp_path / "out", factory)


def test_the_stale_report_is_removed_by_the_sandbox_right_before_the_mutation_step(repo: Path, tmp_path: Path) -> None:
    factory, made = make(lambda argv, project: ExecResult(0, "", ""))
    with pytest.raises(ValueError, match="did not produce"):
        runner.produce(repo, Config(language="javascript"), tmp_path / "out", factory)
    calls = [(c[0][0], c[0][-1]) for c in made[0].calls]
    removal = calls.index(("rm", "/project/.gauntlet-out/stryker.json"))
    assert made[0].calls[removal + 1][0][1].endswith(".bin/stryker")  # the mutation run follows at once
    assert made[0].calls[removal][1:] == ({}, 60) and list(made[0].calls[removal][0][:2]) == ["rm", "-f"]


def test_a_failed_report_removal_stops_the_run(repo: Path, tmp_path: Path) -> None:
    factory, _ = make(lambda argv, project: ExecResult(1 if argv[0] == "rm" else 0, "", "read-only file system"))
    with pytest.raises(ValueError, match="could not clear the old mutation report: read-only file system"):
        runner.produce(repo, Config(language="javascript"), tmp_path / "out", factory)


def test_a_symlinked_output_directory_is_refused_before_anything_is_read(repo: Path, tmp_path: Path) -> None:
    host = tmp_path / "host"
    host.mkdir()
    (host / "coverage.json").write_text('{"files": {}}')

    def behave(argv: Sequence[str], project: Path) -> ExecResult:
        if "pytest" in argv:  # the tests replace .gauntlet-out with a link to a host directory
            shutil.rmtree(project / runner.OUT_DIR)
            (project / runner.OUT_DIR).symlink_to(host)
        return ExecResult(0, "", "")

    factory, _ = make(behave)
    with pytest.raises(ValueError, match=r"\.gauntlet-out is a symlink"):
        runner.produce(repo, Config(language="python"), tmp_path / "out", factory)
