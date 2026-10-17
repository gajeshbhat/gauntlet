"""Pins the exact output of things whose precise wording and shape other tools depend on."""

import json
import os
import re
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest

from gauntlet import runner
from gauntlet.cli import main
from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.report import render
from gauntlet.results import GateResult
from gauntlet.runner import Step
from gauntlet.snapshot import snapshot
from gauntlet.spec import parse


# ---- the commands that run in the sandbox
def test_python_steps_in_full() -> None:
    assert runner.steps(Config("python", src="src"), Path("/unused")) == [
        Step(
            "tests",
            ("uv", "run", "--project", "/project", "--with", "pytest-cov==7.1.0", "pytest", "-q", "--cov=src",
             "--cov-branch", "--cov-report=json:/project/.gauntlet-out/coverage.json"),
            None,
            3600,
            True,
            (),
        ),
        Step(
            "mutation",
            ("uv", "run", "--project", "/project", "--with", "mutmut==3.8.0", "mutmut", "run"),
            None,
            7200,
            False,
            (),
        ),
        Step(
            "mutation-results",
            ("uv", "run", "--project", "/project", "--with", "mutmut==3.8.0", "mutmut", "results", "--all", "true"),
            "mutmut-results.txt",
            1800,
            True,
            (),
        ),
    ]  # fmt: skip


def test_go_steps_in_full(tmp_path: Path) -> None:
    env = (("GOBIN", "/project/.gauntlet-out/bin"), ("GOFLAGS", "-buildvcs=false"))
    c = "-coverprofile=/project/.gauntlet-out/cover.out"
    list_format = '{{.ImportPath}} {{join .Imports " "}}'
    assert runner.steps(Config("go", packages=("./a/...", "./b/")), tmp_path) == [
        Step("install-gremlins", ("go", "install", "github.com/go-gremlins/gremlins/cmd/gremlins@v0.6.0"), None, 1800, True, env),
        Step("tests", ("go", "test", "-count=1", c, "./a/...", "./b/"), None, 3600, True, env),
        Step("imports", ("go", "list", "-e", "-f", list_format, "./a/...", "./b/"), "imports.txt", 1800, True, env),
        Step(
            "mutation",
            ("/project/.gauntlet-out/bin/gremlins", "unleash", "-o", "/project/.gauntlet-out/mutation.json", "."),
            None,
            7200,
            False,
            env,
        ),
    ]  # fmt: skip


def test_go_mutation_scope_excludes_every_other_file(tmp_path: Path) -> None:
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    for name in ("pkg/a.go", "pkg/b.go", "pkg/sub/c.go"):
        (tmp_path / name).write_text("package x\n")
    cfg = Config("go", mutation_dir="pkg", mutate_only=("a.go",))
    mutation = {s.name: s for s in runner.steps(cfg, tmp_path)}["mutation"].argv
    assert mutation == (
        "/project/.gauntlet-out/bin/gremlins", "unleash", "-E", "^b\\.go$", "-E", "^sub/c\\.go$",
        "-o", "/project/.gauntlet-out/mutation.json", "pkg",
    )  # fmt: skip


@pytest.mark.parametrize("bad", ["./a;b", "./$(x)", "./a b", "../a", "./a/../b", "a", "-race", "./a|b"])
def test_unsafe_go_packages(bad: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=f"^unsafe package pattern {re.escape(repr(bad))}$"):
        runner.steps(Config("go", packages=(bad,)), tmp_path)


@pytest.mark.parametrize("good", ["./...", "./a/...", "./a/b/", "./a_b-c.d/..."])
def test_safe_go_packages(good: str, tmp_path: Path) -> None:
    runner.steps(Config("go", packages=(good,)), tmp_path)


@pytest.mark.parametrize("bad", ["../x", "a/../b", "/abs", "a b", "a;b", "-x", ""])
def test_unsafe_paths(bad: str) -> None:
    with pytest.raises(ValueError, match=f"^unsafe path {re.escape(repr(bad))}$"):
        runner.steps(Config("python", src=bad), Path("/unused"))


# ---- the evidence report
def test_report_in_full() -> None:
    results = [
        GateResult("clean", True, "clean: 5 function(s) checked, 0 over CRAP 8"),
        GateResult("arch", False, "arch: 3 module(s) checked, 1 violation(s)", ("a.py:1: x imports outer layer y",)),
    ]
    text = render(
        results,
        language="go",
        fingerprint="f" * 64,
        config_sha256="c" * 64,
        policy=Policy(crap_ceiling=7, mutation_floor=91, max_exclusions=3),
        created="2026-10-16T12:00:00+00:00",
        command="gauntlet run .",
    )
    assert (
        text
        == f"""# Evidence report

Generated 2026-10-16T12:00:00+00:00 by gauntlet {version("gauntlet")}.

- Language: go
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
- Tests run in the sandbox can forge coverage or mutation results; it protects the host, not the numbers.
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
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-q", "-m", "x", "--no-gpg-sign", "--allow-empty"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)
    return root


def run_json(tmp_path: Path, lax: Path, *argv: str) -> list[dict[str, object]]:
    out = tmp_path / "out.json"
    code = main([*argv, "--policy", str(lax), "--json", str(out)])
    assert code in (0, 1)
    return json.loads(out.read_text())


def test_arch_result_shape(tmp_path: Path, lax: Path) -> None:
    root = committed(tmp_path / "r", {})
    (root / "gauntlet.toml").write_text('language = "python"\n[layers]\norder = ["web", "domain"]\n')
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
    (tmp_path / "gauntlet.toml").write_text('language = "python"\n')
    (tmp_path / "a.py").write_text("x = 1  # nosec\n")
    (tmp_path / "pyproject.toml").write_text('[tool.coverage.run]\nomit = ["a.py"]\n')
    assert run_json(tmp_path, lax, "exclusions", str(tmp_path)) == [
        {
            "gate": "exclusions",
            "ok": False,
            "summary": "exclusions: 1 comment(s) (budget 10), 1 config exclude(s)",
            "findings": ["a.py:1: x = 1  # nosec", "pyproject.toml: coverage omit a.py"],
            "stats": {"comments": 1, "config": 1},
        }
    ]


def test_go_exclusions_ignore_python_config(tmp_path: Path, lax: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text('language = "go"\n')
    (tmp_path / "pyproject.toml").write_text('[tool.coverage.run]\nomit = ["a.py"]\n')
    (result,) = run_json(tmp_path, lax, "exclusions", str(tmp_path))
    assert result["stats"] == {"comments": 0, "config": 0}


def test_spec_result_shape(tmp_path: Path, lax: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text('language = "python"\n')
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
    (tmp_path / "gauntlet.toml").write_text('language = "python"\n[layers]\norder = ["web"]\n')
    assert main(["arch", str(tmp_path), "--policy", str(lax)]) == 2
    assert capsys.readouterr().err == "gauntlet: no module belongs to any configured layer; check [layers] and src\n"


# ---- snapshots
def test_snapshot_creates_nested_destinations_and_nested_files(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", {"a/b/c.py": "1\n", "a/b/d.py": "2\n", "a/e.py": "3\n"})
    dest = tmp_path / "deep" / "er" / "snap"
    assert snapshot(repo, dest) == 3
    assert (dest / "a" / "b" / "c.py").read_text() == "1\n"
    assert (dest / "a" / "b" / "d.py").read_text() == "2\n"
    assert dest.stat().st_mode & 0o777 == 0o700


def test_snapshot_accepts_an_existing_empty_destination(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", {"a.py": "1\n"})
    dest = tmp_path / "snap"
    dest.mkdir()
    assert snapshot(repo, dest) == 1


def test_snapshot_limits_are_exact(tmp_path: Path) -> None:
    repo = committed(tmp_path / "repo", {"a.py": "x" * 10, "b.py": "y" * 10})
    assert snapshot(repo, tmp_path / "ok1", max_bytes=20, max_files=2) == 2  # exactly at both limits
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
