from pathlib import Path

from gauntlet import backends
from gauntlet.config import Config
from gauntlet.openshell import OpenShellSandbox
from gauntlet.policy import Policy
from gauntlet.sandbox import LocalSandbox


def test_local_is_the_default(tmp_path: Path) -> None:
    box = backends.gate_sandbox(tmp_path, Config("fake"), Policy())
    assert isinstance(box, LocalSandbox)
    assert box.project_dir == str(tmp_path)


def test_openshell_uses_the_language_image(tmp_path: Path) -> None:
    box = backends.gate_sandbox(tmp_path, Config("fake"), Policy(sandbox="openshell"))
    assert isinstance(box, OpenShellSandbox)
    assert box.image == "example.com/fake:1"
