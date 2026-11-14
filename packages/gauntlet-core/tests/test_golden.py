"""Pins the exact output of things whose precise wording and shape other tools depend on."""

import json
import re
from importlib.metadata import version
from pathlib import Path

import pytest
from helpers import git, tree

from gauntlet import runner
from gauntlet.cli import main
from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.report import render
from gauntlet.results import GateResult
from gauntlet.snapshot import snapshot
from gauntlet.spec import parse


# ---- the commands that run in the sandbox
@pytest.mark.parametrize("bad", ["../x", "a/../b", "/abs", "a b", "a;b", "-x", ""])
def test_unsafe_paths(bad: str) -> None:
    with pytest.raises(ValueError, match=f"^unsafe path {re.escape(repr(bad))}$"):
        runner.steps(Config("fake", src=bad), "/p")


# ---- the evidence report
def test_report_in_full() -> None:
    results = [
        GateResult("clean", True, "clean: 5 function(s) checked, 0 over CRAP 8"),
        GateResult("arch", False, "arch: 3 module(s) checked, 1 violation(s)", ("a.py:1: x imports outer layer y",)),
    ]
    text = render(
        results,
        language="fake",
        scope="mod.py:3-9",
        fingerprint="f" * 64,
        config_sha256="c" * 64,
        policy=Policy(crap_ceiling=7, mutation_floor=91, max_exclusions=3),
        created="2026-10-16T12:00:00+00:00",
        command="gauntlet run .",
    )
    assert (
        text
        == f"""# Evidence report

Generated 2026-10-16T12:00:00+00:00 by gauntlet {version("gauntlet-core")}.

- Language: fake
- Scope: mod.py:3-9
- Source fingerprint: `{"f" * 64}`
- gauntlet.toml sha256: `{"c" * 64}`
- Policy: crap ceiling 7, mutation floor 91, exclusion budget 3

## Gates

| Gate | Result | Summary |
|---|---|---|
| clean | PASS | clean: 5 function(s) checked, 0 over CRAP 8 |
| arch | FAIL | arch: 3 module(s) checked, 1 violation(s) |

**Overall: FAIL**

### arch

- `a.py:1: x imports outer layer y`

## What this does not prove

- The gates measure the code against the configured constraints; they cannot show those constraints are complete.
- Tests can forge coverage or mutation results; a sandbox protects the host, not the numbers.
- Mutation testing samples the mutants its tool generates; a surviving or missing mutant is no proof either way.
- A human should read the spec the tests encode, not only this report.

## Reproduce

```
gauntlet run .
```
"""
    )


# ---- every gate reports in the same, complete shape
def committed(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    tree(root, files)
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-q", "-m", "x", "--no-gpg-sign", "--allow-empty"],
    ):
        git(root, *args)
    return root


def run_json(tmp_path: Path, lax: Path, *argv: str) -> list[dict[str, object]]:
    out = tmp_path / "out.json"
    code = main([*argv, "--policy", str(lax), "--json", str(out)])
    assert code in (0, 1)
    return json.loads(out.read_text())


def test_arch_result_shape(tmp_path: Path, lax: Path) -> None:
    root = committed(tmp_path / "r", {})
    (root / "gauntlet.toml").write_text('language = "fake"\n[layers]\norder = ["web", "domain"]\n')
    (root / "web").mkdir()
    (root / "domain").mkdir()
    (root / "web" / "v.py").write_text("")
    (root / "domain" / "m.py").write_text("from web import v\n")
    assert run_json(tmp_path, lax, "arch", str(root)) == [
        {
            "gate": "arch",
            "ok": False,
            "summary": "arch: 2 module(s) checked, 1 violation(s)",
            "findings": ["domain/m.py:1: domain imports outer layer web"],
            "stats": {"modules": 2, "violations": 1},
        }
    ]


def test_exclusions_result_shape(tmp_path: Path, lax: Path) -> None:
    tree(tmp_path, {"gauntlet.toml": 'language = "fake"\n', "a.py": "x = 1  # nosec\n"})
    (tmp_path / "excludes.txt").write_text("coverage omit a.py\n")
    assert run_json(tmp_path, lax, "exclusions", str(tmp_path)) == [
        {
            "gate": "exclusions",
            "ok": False,
            "summary": "exclusions: 1 comment(s) (budget 10), 1 config exclude(s)",
            "findings": ["a.py:1: x = 1  # nosec", "excludes.txt: coverage omit a.py"],
            "stats": {"comments": 1, "config": 1},
        }
    ]


def test_spec_result_shape(tmp_path: Path, lax: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text('language = "fake"\n')
    (tmp_path / "test_x.py").write_text("def test_it(): pass\n")
    (tmp_path / "spec.feature").write_text(
        "Feature: f\n  @test(test_x.py::test_it)\n  Scenario: s\n    When a\n    Then b\n"
    )
    assert run_json(tmp_path, lax, "spec", str(tmp_path)) == [
        {
            "gate": "spec",
            "ok": True,
            "summary": "spec: 1 scenario(s), 0 problem(s)",
            "findings": [],
            "stats": {"scenarios": 1, "problems": 0},
        }
    ]


def test_arch_with_layers_matching_nothing_message(
    tmp_path: Path, lax: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "gauntlet.toml").write_text('language = "fake"\n[layers]\norder = ["web"]\n')
    assert main(["arch", str(tmp_path), "--policy", str(lax)]) == 2
    assert (
        capsys.readouterr().err
        == "gauntlet: no module under . belongs to any configured layer; check [layers] and roots\n"
    )


# ---- snapshots
def test_snapshot_creates_nested_destinations_and_nested_files(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", {"a/b/c.py": "1\n", "a/b/d.py": "2\n", "a/e.py": "3\n"})
    dest = tmp_path / "deep" / "er" / "snap"
    snapshot(repo, dest)
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == [
        "a/b/c.py",
        "a/b/d.py",
        "a/e.py",
    ]
    assert (dest / "a" / "b" / "c.py").read_text() == "1\n"
    assert (dest / "a" / "b" / "d.py").read_text() == "2\n"
    assert dest.stat().st_mode & 0o777 == 0o700


def test_snapshot_accepts_an_existing_empty_destination(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", {"a.py": "1\n"})
    dest = tmp_path / "snap"
    dest.mkdir()
    snapshot(repo, dest)
    assert (dest / "a.py").read_text() == "1\n"


def test_snapshot_limits_are_exact(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", {"a.py": "x" * 10, "b.py": "y" * 10})
    snapshot(repo, tmp_path / "ok1", max_bytes=20, max_files=2)  # exactly at both limits
    assert sorted(p.name for p in (tmp_path / "ok1").iterdir()) == ["a.py", "b.py"]
    with pytest.raises(ValueError, match="over the 19 byte limit"):
        snapshot(repo, tmp_path / "bad1", max_bytes=19, max_files=2)
    with pytest.raises(ValueError, match="more than 1 files"):
        snapshot(repo, tmp_path / "bad2", max_bytes=20, max_files=1)


# ---- spec parser vocabulary
@pytest.mark.parametrize("keyword", ["Scenario", "Example", "Scenario Outline", "Scenario Template"])
def test_every_scenario_keyword_is_understood(keyword: str) -> None:
    feature = parse(f"Feature: x\n  {keyword}: with: colon\n    When a\n    Then b\n")
    assert feature.problems == ()
    assert [s.name for s in feature.scenarios] == ["with: colon"]
    assert feature.scenarios[0].outline is keyword.startswith("Scenario ")


def test_examples_and_scenarios_keywords() -> None:
    for keyword in ("Examples", "Scenarios"):
        text = (
            f"Feature: x\n  Scenario Outline: o\n    When <a>\n    Then b\n    {keyword}:\n      | a |\n      | 1 |\n"
        )
        assert parse(text).scenarios[0].examples == (("a",), ("1",))


def test_feature_name_may_contain_colons_and_first_name_wins() -> None:
    assert parse("Feature: a: b\n").name == "a: b"


def test_star_steps_repeat_the_previous_keyword() -> None:
    feature = parse("Feature: x\n  Scenario: s\n    When a\n    * b\n    Then c\n")
    assert [k for k, _ in feature.scenarios[0].steps] == ["When", "When", "Then"]


def test_a_new_scenario_resets_the_step_keyword() -> None:
    feature = parse("Feature: x\n  Scenario: s\n    Then a\n  Scenario: t\n    And b\n")
    assert feature.scenarios[1].steps == (("Given", "b"),)
