import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from gauntlet import openshell
from gauntlet.errors import GauntletError
from gauntlet.openshell import OpenShellSandbox


class FakeBox:
    """The SDK's sandbox, with the sandbox's filesystem being a directory on this machine."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail: str | None = None
        self.garble: str | None = None
        self.exited = 0

    def __enter__(self) -> "FakeBox":
        return self

    def __exit__(self, *args: object) -> None:
        self.exited += 1

    def exec(self, argv: Sequence[str], **kw: Any) -> SimpleNamespace:
        self.calls.append({"argv": list(argv), **kw})
        if argv[0] == self.fail:
            return SimpleNamespace(exit_code=1, stdout="", stderr="boom")
        if argv[0] == self.garble:
            return SimpleNamespace(exit_code=0, stdout="!!!", stderr="")
        try:
            done = subprocess.run(
                list(argv), input=kw.get("stdin"), cwd=kw["workdir"], env={**os.environ, **kw["env"]}, capture_output=True,
                timeout=kw["timeout_seconds"],
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            return SimpleNamespace(exit_code=124, stdout="", stderr="timed out")
        return SimpleNamespace(exit_code=done.returncode, stdout=done.stdout.decode(), stderr=done.stderr.decode())


World = tuple[OpenShellSandbox, FakeBox, Path]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setattr(openshell, "CHUNK", 64)  # several calls per transfer
    host = tmp_path / "snap"
    (host / ".gauntlet-out").mkdir(parents=True)
    (host / "a.py").write_text("x = 1\n" * 200)
    (host / "pkg").mkdir()
    (host / "pkg" / "b.py").write_text("y = 2\n")
    fake, root = FakeBox(), tmp_path / "sbx"
    root.mkdir()
    return OpenShellSandbox(host, "img:1", root=str(root), connect=lambda name, image: fake), fake, root


def test_ensure_copies_the_snapshot_in_small_pieces(world: World) -> None:
    box, fake, root = world
    box.ensure()
    assert box.project_dir == f"{root}/project"
    assert (root / "project" / "a.py").read_text() == "x = 1\n" * 200
    assert (root / "project" / "pkg" / "b.py").read_text() == "y = 2\n"
    assert not (root / "gauntlet.tar").exists()
    sent = [len(c["stdin"]) for c in fake.calls if c.get("stdin")]
    assert len(sent) > 5 and max(sent) <= 64


def test_exec_runs_in_the_project_with_the_resolved_environment(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    box, fake, _ = world
    monkeypatch.setenv("TOKEN", "t")
    box.ensure()
    done = box.exec(["sh", "-c", "echo $TOKEN $PLAIN; pwd"], {"TOKEN": None, "PLAIN": "p"}, 42)
    assert done.code == 0 and done.stdout.split() == ["t", "p", box.project_dir]
    assert (fake.calls[-1]["workdir"], fake.calls[-1]["timeout_seconds"]) == (box.project_dir, 42)
    assert fake.calls[-1]["env"] == {"TOKEN": "t", "PLAIN": "p"}


def test_a_timeout_is_reported_as_exit_124(world: World) -> None:
    box, _, _ = world
    box.ensure()
    assert box.exec(["sleep", "30"], timeout=1).code == 124


def test_fetch_replaces_a_directory_with_the_sandboxs_copy(world: World) -> None:
    box, _, root = world
    box.ensure()
    (root / "project" / ".gauntlet-out" / "coverage.json").write_text('{"files": {}}' * 30)
    (box.project / ".gauntlet-out" / "stale.txt").write_text("old")
    box.fetch(".gauntlet-out")
    assert (box.project / ".gauntlet-out" / "coverage.json").read_text() == '{"files": {}}' * 30
    assert not (box.project / ".gauntlet-out" / "stale.txt").exists()


def test_fetch_replaces_a_leftover_that_is_not_a_directory(world: World) -> None:
    box, _, root = world
    box.ensure()
    (root / "project" / ".gauntlet-out" / "coverage.json").write_text("{}")
    shutil.rmtree(box.project / ".gauntlet-out")
    (box.project / ".gauntlet-out").symlink_to("elsewhere")
    box.fetch(".gauntlet-out")
    assert (box.project / ".gauntlet-out" / "coverage.json").read_text() == "{}"


def test_a_hostile_archive_is_refused(world: World) -> None:
    box, _, root = world
    box.ensure()
    (root / "project" / ".gauntlet-out" / "x").symlink_to("/etc/passwd")
    with pytest.raises(GauntletError, match=r"^the sandbox returned a damaged copy of \.gauntlet-out$"):
        box.fetch(".gauntlet-out")


def test_garbled_output_is_refused(world: World) -> None:
    box, fake, _ = world
    box.ensure()
    fake.garble = "dd"
    with pytest.raises(GauntletError, match="damaged copy"):
        box.fetch(".gauntlet-out")


def test_a_huge_copy_is_refused(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    box, _, _ = world
    box.ensure()
    monkeypatch.setattr(openshell, "MAX_FETCH", 1)
    with pytest.raises(GauntletError, match=r"^\.gauntlet-out is too big to copy out of the sandbox$"):
        box.fetch(".gauntlet-out")


def test_a_failing_helper_command_names_itself_and_its_error(world: World) -> None:
    box, fake, _ = world
    fake.fail = "mkdir"
    with pytest.raises(GauntletError, match=r"^mkdir failed in the sandbox: boom$"):
        box.ensure()


def test_a_sandbox_that_will_not_start_is_a_clean_error_with_a_hint(tmp_path: Path) -> None:
    def down(name: str, image: str) -> Any:
        raise ConnectionError("gateway unreachable")

    with pytest.raises(GauntletError, match=r"cannot start an OpenShell sandbox: gateway unreachable; install the SDK"):
        OpenShellSandbox(tmp_path, "img", connect=down).ensure()


def test_our_own_errors_pass_through_unchanged(tmp_path: Path) -> None:
    def missing(name: str, image: str) -> Any:
        raise GauntletError("the openshell SDK is not installed")

    with pytest.raises(GauntletError, match=r"^the openshell SDK is not installed$"):
        OpenShellSandbox(tmp_path, "img", connect=missing).ensure()


def test_remove_leaves_the_sandbox_once_and_is_safe_before_ensure(world: World) -> None:
    box, fake, _ = world
    box.remove()
    assert fake.exited == 0
    box.ensure()
    box.remove()
    box.remove()
    assert fake.exited == 1


def test_names_are_unique_per_sandbox(tmp_path: Path) -> None:
    names: list[str] = []

    def record(name: str, image: str) -> Any:
        names.append(name)
        raise GauntletError("stop")

    for _ in range(2):
        with pytest.raises(GauntletError):
            OpenShellSandbox(tmp_path, "img", connect=record).ensure()
    assert names[0] != names[1] and all(n.startswith("gauntlet-") for n in names)


# ---- the SDK glue, against stand-in modules
def make(**kw: object) -> dict[str, object]:
    return kw


def stub_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    modules = {
        "openshell": SimpleNamespace(Sandbox=make),
        "openshell._proto.openshell_pb2": SimpleNamespace(SandboxSpec=make, SandboxTemplate=make),
        "openshell._proto.sandbox_pb2": SimpleNamespace(
            SandboxPolicy=make, FilesystemPolicy=make, NetworkPolicyRule=make, NetworkEndpoint=make, NetworkBinary=make
        ),
    }

    def find(name: str) -> SimpleNamespace:
        return modules[name]

    monkeypatch.setattr(openshell, "import_module", find)


def test_the_gateway_sandbox_allows_the_package_index_to_uv_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_sdk(monkeypatch)
    made: Any = openshell.gateway("n", "img:1")
    assert (made["workspace"], made["name"], made["delete_on_exit"]) == ("default", "n", True)
    spec = made["spec"]
    assert spec["template"] == {"image": "img:1"}
    assert "/dev/shm" in spec["policy"]["filesystem"]["read_write"]  # mutmut's worker pool needs shared memory
    (pypi,) = spec["policy"]["network_policies"].values()
    assert [e["host"] for e in pypi["endpoints"]] == ["pypi.org", "files.pythonhosted.org"]
    assert pypi["binaries"] == [{"path": "/usr/local/bin/uv"}]


def test_a_missing_sdk_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(openshell, "import_module", gone)
    with pytest.raises(GauntletError, match=r"openshell SDK is not installed.*gauntlet-core\[openshell\]"):
        openshell.gateway("n", "img")
