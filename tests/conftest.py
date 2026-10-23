from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet.cli import main


@pytest.fixture(autouse=True)
def isolated_policy(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read the developer's real ~/.config/gauntlet/policy.toml."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg")))
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture
def write_policy(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Path]:
    def write(text: str) -> Path:
        path = tmp_path_factory.mktemp("policy") / "policy.toml"
        path.write_text(text)
        return path

    return write


@pytest.fixture
def lax(write_policy: Callable[[str], Path]) -> Path:
    """A policy that accepts artifacts without provenance, for tests that are not about provenance."""
    return write_policy("allow_unstamped = true\n")


@pytest.fixture
def cli_run(lax: Path) -> Callable[..., int]:
    """`gauntlet <argv>` under the lax policy."""
    return lambda *argv: main([*map(str, argv), "--policy", str(lax)])
