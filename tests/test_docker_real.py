"""Runs real containers. Opt in with GAUNTLET_DOCKER_TESTS=1 (needs Docker and network to pull the image)."""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet import languages
from gauntlet.cli import main
from gauntlet.docker import DockerSandbox

pytestmark = pytest.mark.skipif(os.environ.get("GAUNTLET_DOCKER_TESTS") != "1", reason="set GAUNTLET_DOCKER_TESTS=1")


@pytest.fixture
def box(tmp_path: Path):  # type: ignore[no-untyped-def]  # noqa: ANN201
    sandbox = DockerSandbox(tmp_path, languages.TABLE["python"].image, memory="512m")
    sandbox.ensure()
    yield sandbox
    sandbox.remove()


def test_container_is_hardened_and_sees_only_the_project(box: DockerSandbox, tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("hi")
    probe = (
        "grep CapEff /proc/self/status; grep NoNewPrivs /proc/self/status; cat /sys/fs/cgroup/memory.max; ls /project"
    )
    out = box.exec(["sh", "-c", probe]).stdout
    assert "CapEff:\t0000000000000000" in out
    assert "NoNewPrivs:\t1" in out
    assert "536870912" in out
    assert "marker.txt" in out


def test_a_runaway_command_is_stopped(box: DockerSandbox) -> None:
    assert box.exec(["sleep", "30"], timeout=2).code == 124


def test_host_environment_does_not_leak_and_named_secrets_do_not_appear_in_argv(
    box: DockerSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GAUNTLET_TEST_SECRET", "s3cret")
    assert box.exec(["sh", "-c", "echo [${GAUNTLET_TEST_SECRET}]"]).stdout.strip() == "[]"
    assert (
        box.exec(["sh", "-c", "echo [${GAUNTLET_TEST_SECRET}]"], env={"GAUNTLET_TEST_SECRET": None}).stdout.strip()
        == "[s3cret]"
    )


JS_FILES = {
    "package.json": '{"name":"demo","version":"1.0.0","scripts":{"test":"node --test"}}',
    "package-lock.json": '{"name":"demo","version":"1.0.0","lockfileVersion":3,"requires":true,'
    '"packages":{"":{"name":"demo","version":"1.0.0"}}}',
    "gauntlet.toml": 'language = "javascript"',
    "index.js": "function f(x) {\n  if (x > 1) { return 1; }\n  return 0;\n}\n"
    + "function risky(a) {\n"
    + "".join(f"  if (a === {i}) {{ return {i}; }}\n" for i in range(1, 6))
    + "  return 0;\n}\nmodule.exports = { f, risky };\n",
    "index.test.js": 'const t = require("node:test"), a = require("node:assert"), { f } = require("./index.js");\n'
    't("f", () => { a.strictEqual(f(2), 1); a.strictEqual(f(0), 0); });\n',
}


def test_javascript_project_runs_through_c8_in_a_real_container(
    tmp_path: Path, write_policy: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    for name, text in JS_FILES.items():
        (tmp_path / name).write_text(text)
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "x", "--no-gpg-sign"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True)
    assert main(["run", str(tmp_path), "--policy", str(write_policy('sandbox = "docker"\n'))]) == 1
    out = capsys.readouterr().out
    assert "index.js:5: risky CRAP 42.0 > 8 (complexity 6, coverage 0%)" in out
    assert "harden: SKIPPED" in out
