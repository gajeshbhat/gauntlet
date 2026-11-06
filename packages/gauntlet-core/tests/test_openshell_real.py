"""Against a real OpenShell gateway; skipped unless the SDK is installed and a gateway answers."""

import os
from importlib import import_module
from pathlib import Path

import pytest

from gauntlet.openshell import OpenShellSandbox

REAL_ENV = {k: os.environ.get(k) for k in ("HOME", "XDG_CONFIG_HOME")}  # before conftest isolates them
IMAGE = "ghcr.io/astral-sh/uv:python3.12-bookworm"


def gateway_up() -> bool:
    try:
        import_module("openshell").SandboxClient.from_active_cluster().close()
    except Exception:  # no SDK, no gateway, no credentials: all mean "not here"
        return False
    return True


@pytest.mark.skipif(not gateway_up(), reason="needs the openshell SDK and a running gateway")
def test_a_project_goes_in_results_come_out_and_only_the_package_index_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in REAL_ENV.items():  # the SDK finds the gateway through the real config directory
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    (tmp_path / "out").mkdir()
    (tmp_path / "hello.txt").write_text("hi\n" * 400_000)  # bigger than one call carries
    box = OpenShellSandbox(tmp_path, IMAGE)
    try:
        box.ensure()
        assert box.exec(["sh", "-c", "wc -c < hello.txt; id -u; pwd"]).stdout.split() == [
            "1200000",
            "1000",
            box.project_dir,
        ]
        assert box.exec(["sh", "-c", "uv --version && echo done > out/result.txt"]).code == 0
        assert box.exec(["sleep", "30"], timeout=2).code == 124
        net = "import urllib.request as u; u.urlopen('https://example.com', timeout=8)"
        assert box.exec(["python3", "-c", net]).code != 0
        box.fetch("out")
    finally:
        box.remove()
    assert (tmp_path / "out" / "result.txt").read_text() == "done\n"
