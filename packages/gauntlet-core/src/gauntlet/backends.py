"""Map the config and policy onto a sandbox: this machine, or an OpenShell sandbox over the language's image."""

from pathlib import Path

from gauntlet import languages
from gauntlet.config import Config
from gauntlet.openshell import OpenShellSandbox
from gauntlet.policy import Policy
from gauntlet.sandbox import LocalSandbox, Sandbox


def gate_sandbox(project: Path, cfg: Config, policy: Policy) -> Sandbox:
    """Where `gauntlet run` executes the project's tests and mutation testing."""
    if policy.sandbox == "openshell":
        return OpenShellSandbox(project, languages.get(cfg.language).image)
    return LocalSandbox(project)
