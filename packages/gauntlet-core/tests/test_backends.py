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


def test_openshell_uses_the_language_image_and_gives_only_the_agent_extra_hosts(tmp_path: Path) -> None:
    pol = Policy(sandbox="openshell", agent_hosts=("api.example.com",))
    gate = backends.gate_sandbox(tmp_path, Config("fake"), pol)
    agent = backends.agent_sandbox(tmp_path, Config("fake"), pol)
    assert isinstance(gate, OpenShellSandbox) and isinstance(agent, OpenShellSandbox)
    assert (gate.image, gate.hosts) == ("example.com/fake:1", ())
    assert (agent.image, agent.hosts) == ("example.com/fake:1", ("api.example.com",))
