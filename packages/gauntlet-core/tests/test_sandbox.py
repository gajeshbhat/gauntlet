import sys
import time
from pathlib import Path

import pytest

from gauntlet.sandbox import ExecResult, LocalSandbox, resolve


def python(
    box: LocalSandbox, code: str, *args: str, env: dict[str, str | None] | None = None, timeout: int = 60
) -> ExecResult:
    return box.exec([sys.executable, "-c", code, *args], env, timeout)


def test_a_command_runs_in_the_snapshot_and_its_output_is_returned(tmp_path: Path) -> None:
    box = LocalSandbox(tmp_path)
    assert box.project_dir == str(tmp_path)
    done = python(box, "import os,sys; print(os.getcwd()); print('e', file=sys.stderr); sys.exit(3)")
    assert (done.code, done.stdout.strip(), done.stderr.strip()) == (3, str(tmp_path.resolve()), "e")


def test_arguments_are_never_interpreted_by_a_shell(tmp_path: Path) -> None:
    done = python(LocalSandbox(tmp_path), "import sys; print(sys.argv[1])", "$(echo hacked); `id`")
    assert done.stdout.strip() == "$(echo hacked); `id`"


def test_the_environment_is_scrubbed_to_what_the_tools_need(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "AWS_SECRET_ACCESS_KEY": "s3cret",
        "UV_CACHE_DIR": "/c",
        "VIRTUAL_ENV": "/v",
        "TOKEN": "t",
    }.items():
        monkeypatch.setenv(name, value)
    code = "import os; print(*sorted(k for k in os.environ if k in 'AWS_SECRET_ACCESS_KEY UV_CACHE_DIR VIRTUAL_ENV PATH HOME TOKEN EXTRA GONE'.split()))"
    done = python(LocalSandbox(tmp_path), code, env={"EXTRA": "1", "TOKEN": None, "GONE": None})
    assert done.stdout.split() == ["EXTRA", "HOME", "PATH", "TOKEN", "UV_CACHE_DIR"]


def test_a_bare_name_takes_its_value_from_our_environment_or_is_left_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAVE", "yes")
    monkeypatch.delenv("MISSING", raising=False)
    assert resolve({"HAVE": None, "MISSING": None, "SET": "v"}) == {"HAVE": "yes", "SET": "v"}


def test_a_timeout_ends_the_whole_process_group_with_exit_124(tmp_path: Path) -> None:
    code = "import subprocess,time; subprocess.Popen(['sleep','30']); time.sleep(30)"
    start = time.monotonic()
    done = python(LocalSandbox(tmp_path), code, timeout=1)
    assert (done.code, done.stderr) == (124, "timed out after 1s")
    assert time.monotonic() - start < 10  # the grandchild did not keep the pipes open


def test_a_missing_program_is_exit_127_not_a_crash(tmp_path: Path) -> None:
    done = LocalSandbox(tmp_path).exec(["no-such-program-gauntlet"])
    assert (done.code, done.stdout) == (127, "")
    assert done.stderr.startswith("no-such-program-gauntlet: ")


def test_stdin_is_closed(tmp_path: Path) -> None:
    assert python(LocalSandbox(tmp_path), "import sys; print(repr(sys.stdin.read()))").stdout.strip() == "''"


def test_ensure_fetch_and_remove_have_nothing_to_do(tmp_path: Path) -> None:
    box = LocalSandbox(tmp_path)
    box.ensure()
    box.fetch(".")
    box.remove()
    assert tmp_path.exists()
