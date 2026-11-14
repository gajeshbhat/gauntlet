"""The Cosmic Ray side: the reader, the plugin wiring, and the sandbox scripts, run for real in a subprocess."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from gauntlet import harden
from gauntlet.plugin import Step
from gauntlet.results import Mutation
from gauntlet.scope import Scope, parse
from gauntlet_python import LANGUAGE
from gauntlet_python.cosmic import TOOL, locate
from gauntlet_python.steps import CONFIGURE_CR, DUMP_CR, RUN_CR, steps

RESULTS = """
src/a.py:2 core/Op_Add_Sub: killed
src/a.py:3 core/Op_Add_Mul: incompetent
src/a.py:4 core/Op_Eq_NotEq: survived
src/a.py:5 core/Op_Lt_Gt: abnormal
src/a.py:6 core/Op_Gt_Lt: no-test
"""


def check(results: str) -> Mutation:
    return harden.check(results, TOOL, Path("unused"), Scope())


def test_killed_and_incompetent_are_caught_and_no_test_is_ignored() -> None:
    result = check(RESULTS)
    assert (result.caught, result.total, result.pct) == (2, 4, 50.0)
    assert result.survivors == ["src/a.py:4 core/Op_Eq_NotEq: survived", "src/a.py:5 core/Op_Lt_Gt: abnormal"]


def test_no_mutants_is_an_error() -> None:
    with pytest.raises(ValueError, match=r"^no mutants found; does \[mutation\] tool = \"cosmic-ray\" see any source"):
        check("src/a.py:6 core/Op_Gt_Lt: no-test\n")


@pytest.mark.parametrize("status", ["abnormal", "exception", "pending"])
def test_when_no_mutant_ever_ran_cosmic_ray_did_not_work(status: str) -> None:
    with pytest.raises(ValueError, match=r"^cosmic-ray ran no mutant: its workers.*`cosmic-ray exec` in the project"):
        check(f"src/a.py:2 core/Op: {status}\n")


def test_a_few_abnormal_mutants_among_checked_ones_are_survivors_not_an_error() -> None:
    assert check("a: killed\nb: exception\n").pct == 50.0


def test_a_mutant_is_on_the_line_its_name_starts_with() -> None:
    names = ["src/a.py:4 core/Op_Eq_NotEq", "C:/a.py:12 core/Op two", "src/a.py:x core/Op", ":3 core/Op", "plain"]
    assert locate(names, Path("unused")) == {names[0]: ("src/a.py", 4, 4), names[1]: ("C:/a.py", 12, 12)}


def test_a_scope_keeps_only_the_mutants_on_its_lines() -> None:
    scoped = harden.check(RESULTS, TOOL, Path("unused"), parse(["src/a.py:3-4"]))
    assert (scoped.caught, scoped.total) == (1, 2)
    assert scoped.survivors == ["src/a.py:4 core/Op_Eq_NotEq: survived"]


def test_the_plugin_offers_both_tools_under_one_artifact() -> None:
    assert list(LANGUAGE.mutation) == ["mutmut", "cosmic-ray"]
    assert {t.artifact for t in LANGUAGE.mutation.values()} == {"mutmut-results.txt"}
    assert LANGUAGE.mutation["cosmic-ray"] is TOOL
    assert TOOL.how == 'set [mutation] tool = "cosmic-ray" and run: gauntlet run'


def test_cosmic_ray_steps_in_full() -> None:
    project, out = "/tmp/snap", "/tmp/snap/.gauntlet-out"
    uv = ("uv", "run", "--no-project", "--with", "cosmic-ray==8.7.0", "python3", "-I", "-c")
    env = (("SETUPTOOLS_SCM_PRETEND_VERSION", "0.0.0"),)
    plan = steps("src", project, out, "cosmic-ray", ())
    assert plan[0] == steps("src", project, out, "mutmut", ())[0]  # the tests step is shared
    assert plan[1:] == [
        Step("mutation-config", ("python3", "-I", "-c", CONFIGURE_CR, project, "src", out), None, 60, True, ()),
        Step("mutation", (*uv, RUN_CR, project, out), None, 7200, True, env),
        Step("mutation-results", (*uv, DUMP_CR, "cosmic-ray", "dump", f"{out}/session.sqlite"),
             "mutmut-results.txt", 1800, True, env),
    ]  # fmt: skip


def test_with_files_in_scope_cosmic_ray_is_told_which() -> None:
    plan = steps("src", "/p", "/p/out", "cosmic-ray", ("src/a.py", "src/b.py"))
    assert plan[1].argv[-5:] == ("/p", "src", "/p/out", "src/a.py", "src/b.py")


# ---- sandbox scripts
def test_with_files_in_scope_the_config_lists_only_those(tmp_path: Path) -> None:
    for name in ("src/p/a.py", "src/p/b.py", "src/p/test_c.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x = 1\n")
    only = ["src/p/b.py", "src/p/test_c.py", "elsewhere.py"]  # a test or a file outside src is never mutated
    subprocess.run([sys.executable, "-c", CONFIGURE_CR, str(tmp_path), "src", str(tmp_path), *only], check=True)
    assert 'module-path = ["src/p/b.py"]' in (tmp_path / "cosmic-ray.toml").read_text()


def test_the_config_lists_mutable_files_only(tmp_path: Path) -> None:
    for name in (
        "src/p/a.py",
        "src/p/sub/b.py",
        "src/p/tests/t.py",
        "src/p/test_c.py",
        "src/conftest.py",
        "src/.v/d.py",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x = 1\n")
    out = tmp_path / "out"
    out.mkdir()
    subprocess.run([sys.executable, "-c", CONFIGURE_CR, str(tmp_path), "src", str(out)], check=True)
    import tomllib

    config = tomllib.loads((out / "cosmic-ray.toml").read_text())["cosmic-ray"]
    assert config["module-path"] == ["src/p/a.py", "src/p/sub/b.py"]
    assert config["test-command"].startswith("uv run --project . ")
    assert set(config) == {"module-path", "test-command"}  # run.py adds the timeout and the distributor


DUMP = [
    [{"mutations": [{"module_path": "src/a.py", "operator_name": "core/Op", "start_pos": [2, 1]}]},
     {"worker_outcome": "normal", "test_outcome": "killed", "output": "x" * 5000, "diff": "y" * 5000}],
    [{"mutations": [{"module_path": "src/a.py", "operator_name": "core/Op", "start_pos": [3, 1]}]},
     {"worker_outcome": "no-test", "test_outcome": None}],
    [{"mutations": [{"module_path": "src/a.py", "operator_name": "core/Op", "start_pos": [4, 1]}]}, None],
]  # fmt: skip


def test_the_dump_is_one_short_line_per_mutant() -> None:
    fake = "import json, sys\nfor row in json.loads(sys.argv[1]): print(json.dumps(row))"
    done = subprocess.run(
        [sys.executable, "-c", DUMP_CR, sys.executable, "-c", fake, json.dumps(DUMP)], capture_output=True, text=True
    )
    assert done.stdout.splitlines() == [
        "src/a.py:2 core/Op: killed",
        "src/a.py:3 core/Op: no-test",
        "src/a.py:4 core/Op: pending",
    ]


FAKE_CR = """#!{python}
import json, os, socket, sys, time
log = os.path.join(os.environ["CR_LOG"], "calls.jsonl")
with open(log, "a") as f:
    f.write(json.dumps([os.getcwd(), *sys.argv[1:]]) + "\\n")
mode = os.environ.get("CR_MODE", "")
if sys.argv[1] == "baseline":
    print("boom: baseline", file=sys.stderr) if mode == "baseline" else None
    sys.exit(1 if mode == "baseline" else 0)
if sys.argv[1] == "http-worker":
    if mode == "worker-dies":
        sys.exit(3)
    if mode == "worker-hangs":
        time.sleep(100)
    server = socket.socket()
    server.bind(("127.0.0.1", int(sys.argv[3])))
    server.listen()
    time.sleep(100)
if sys.argv[1] == "exec" and mode == "exec":
    print("exec exploded", file=sys.stderr)
    sys.exit(1)
"""


def _run_cr(tmp_path: Path, mode: str, ready: int = 600) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    project, bin_dir = tmp_path / "project", tmp_path / "bin"
    (project / "src").mkdir(parents=True)
    (project / "src" / "a.py").write_text("x = 1\n")
    (project / ".gauntlet-out").mkdir()
    (project / ".gauntlet-out" / "cosmic-ray.toml").write_text('[cosmic-ray]\nmodule-path = ["src/a.py"]\n')
    bin_dir.mkdir()
    fake = bin_dir / "cosmic-ray"
    fake.write_text(FAKE_CR.format(python=sys.executable))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "log").mkdir()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CR_LOG": str(tmp_path / "log"),
        "CR_MODE": mode,
    }
    script = RUN_CR.replace("range(600)", f"range({ready})")  # the fake that hangs must not take a minute
    done = subprocess.run(
        [sys.executable, "-c", script, str(project), str(project / ".gauntlet-out")],
        capture_output=True,
        text=True,
        env=env,
    )
    log = tmp_path / "log" / "calls.jsonl"
    return done, [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_cosmic_ray_runs_baseline_then_one_worker_per_cpu_then_init_and_exec(tmp_path: Path) -> None:
    done, calls = _run_cr(tmp_path, "")
    assert done.returncode == 0, done.stderr
    workers = len(os.sched_getaffinity(0))
    assert [c[1] for c in calls] == ["baseline", *["http-worker"] * workers, "init", "exec"]
    assert len({c[0] for c in calls if c[1] == "http-worker"}) == workers  # each worker has its own copy
    assert all(not Path(c[0]).exists() for c in calls if c[1] == "http-worker")  # and they are cleaned up
    final = (tmp_path / "project" / ".gauntlet-out" / "run.toml").read_text()
    assert final.count("http://127.0.0.1:") == workers
    assert 'name = "http"' in final and "timeout = " in final
    assert [c[3] for c in calls if c[1] == "init"] == [str(tmp_path / "project" / ".gauntlet-out" / "session.sqlite")]


def test_failing_tests_on_the_unmutated_code_are_a_clear_error(tmp_path: Path) -> None:
    done, calls = _run_cr(tmp_path, "baseline")
    assert done.returncode == 1
    assert "the tests fail on the unmutated code" in done.stderr and "boom: baseline" in done.stderr
    assert [c[1] for c in calls] == ["baseline"]  # no worker was started


def test_a_worker_that_dies_is_a_clear_error_and_the_rest_are_stopped(tmp_path: Path) -> None:
    done, calls = _run_cr(tmp_path, "worker-dies")
    assert done.returncode == 1
    assert "a cosmic-ray worker exited with code 3 before it was ready" in done.stderr
    assert "exec" not in [c[1] for c in calls]


def test_a_worker_that_never_listens_is_a_clear_error(tmp_path: Path) -> None:
    done, _ = _run_cr(tmp_path, "worker-hangs", ready=3)
    assert done.returncode == 1
    assert "did not listen on port" in done.stderr


def test_a_failing_exec_is_a_clear_error(tmp_path: Path) -> None:
    done, _ = _run_cr(tmp_path, "exec")
    assert done.returncode == 1
    assert "cosmic-ray exec failed" in done.stderr and "exec exploded" in done.stderr
