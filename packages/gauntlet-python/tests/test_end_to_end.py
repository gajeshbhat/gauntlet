"""The real Python plugin, found through the entry-point registry, driven through the gauntlet CLI."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pyhelpers import tree

from gauntlet.cli import main

BRANCHY = "def g(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(1, 8)) + "    return 0\n"


@pytest.fixture
def run(tmp_path: Path) -> Callable[..., int]:
    policy = tmp_path / "policy.toml"
    policy.write_text("allow_unstamped = true\nmutation_floor = 50\n")
    return lambda *argv: main([*map(str, argv), "--policy", str(policy)])


def project(root: Path, covered: bool, extra: dict[str, str] | None = None) -> Path:
    tree(root, {"pyproject.toml": "[project]\nname = 'x'\n", "mod.py": BRANCHY, **(extra or {})})
    executed, missing = (list(range(1, 17)), []) if covered else ([1], list(range(2, 17)))
    cov = {"files": {"mod.py": {"executed_lines": executed, "missing_lines": missing}}}
    (root / "coverage.json").write_text(json.dumps(cov))
    return root


def test_init_detects_python_then_clean_reads_a_coveragepy_report(
    tmp_path: Path, run: Callable[..., int], capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path / "bad", covered=False)
    assert run("init", root) == 0
    assert 'language = "python"' in (root / "gauntlet.toml").read_text()
    assert run("clean", root) == 1
    assert "mod.py:1: g CRAP" in capsys.readouterr().out

    good = project(tmp_path / "good", covered=True)
    assert run("init", good) == 0
    assert run("clean", good) == 0


def test_arch_reads_real_python_imports(tmp_path: Path, run: Callable[..., int]) -> None:
    root = project(
        tmp_path / "r",
        covered=True,
        extra={
            "gauntlet.toml": 'language = "python"\n[layers]\norder = ["web", "domain"]\n',
            "web/__init__.py": "",
            "domain/m.py": "from web import v\n",
        },
    )
    assert run("arch", root) == 1


def test_mutation_results_are_read_by_the_plugin(
    tmp_path: Path, run: Callable[..., int], capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(
        tmp_path / "m",
        covered=True,
        extra={"mutmut-results.txt": "    x.a__mutmut_1: killed\n    x.a__mutmut_2: survived\n"},
    )
    assert run("init", root) == 0
    assert run("harden", root) == 0
    assert "mutation score 50.0% >= 50%" in capsys.readouterr().out
