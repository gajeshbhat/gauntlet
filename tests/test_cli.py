import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from gauntlet import cli
from gauntlet.cli import main
from gauntlet.config import Config
from gauntlet.policy import Policy
from gauntlet.sandbox import ExecResult

BRANCHY = "def g(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(1, 8)) + "    return 0\n"


def _go_branches(name: str, count: int) -> list[str]:
    body = [line for i in range(count) for line in (f"\tif x == {i} {{", f"\t\treturn {i}", "\t}")]
    return [f"func {name}(x int) int {{", *body, "\treturn 0", "}"]


GO_SOURCE = "\n".join(
    ["package device", *[""] * 26, *_go_branches("DiskMount", 17), *[""] * 13, *_go_branches("Small", 5)]
)
GO_COVER = (
    "mode: set\nexample.com/m/lxd/device/disk.go:28.1,81.2 1 0\nexample.com/m/lxd/device/disk.go:95.1,112.2 1 1\n"
)
Out = pytest.CaptureFixture[str]


def project(root: Path, toml: str) -> Path:
    (root / "gauntlet.toml").write_text(toml)
    return root


def py_project(root: Path, toml: str = 'language = "python"\n', covered: bool = False) -> Path:
    project(root, toml)
    (root / "mod.py").write_text(BRANCHY)
    missing = [] if covered else list(range(2, 17))
    executed = list(range(1, 17)) if covered else [1]
    cov = {"files": {"mod.py": {"executed_lines": executed, "missing_lines": missing}}}
    (root / "coverage.json").write_text(json.dumps(cov))
    return root


def go_project(root: Path, extra: str = "") -> Path:
    project(root, 'language = "go"\n[layers]\norder = ["m/web", "m/domain"]\n' + extra)
    (root / "lxd" / "device").mkdir(parents=True)
    (root / "lxd" / "device" / "disk.go").write_text(GO_SOURCE + "\n")
    (root / "cover.out").write_text(GO_COVER)
    (root / "imports.txt").write_text("m/domain m/web\n")
    return root


@pytest.fixture
def cli_run(lax: Path) -> Callable[..., int]:
    return lambda *argv: main([*map(str, argv), "--policy", str(lax)])


# ---- usage and errors
def test_unknown_gate_exits_with_usage_error() -> None:
    with pytest.raises(SystemExit) as e:
        main(["bogus"])
    assert e.value.code == 2


def test_usage_names_the_program(capsys: Out) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert capsys.readouterr().out.startswith("usage: gauntlet")


def test_missing_config_exits_2(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("arch", tmp_path) == 2
    assert "gauntlet.toml" in capsys.readouterr().err


def test_bad_scope_is_a_usage_error(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", py_project(tmp_path), "--only", "x.py:9-1") == 2
    assert "scope" in capsys.readouterr().err


def test_root_defaults_to_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_run: Callable[..., int]
) -> None:
    py_project(tmp_path, covered=True)
    monkeypatch.chdir(tmp_path)
    assert cli_run("clean") == 0


def test_malformed_input_is_a_clean_error(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path)
    (tmp_path / "coverage.json").write_text("{}")
    assert cli_run("clean", tmp_path) == 2
    assert "cannot read coveragepy report" in capsys.readouterr().err


# ---- arch
def test_arch_fails_on_outward_import(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "web").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "web" / "v.py").write_text("")
    (tmp_path / "domain" / "m.py").write_text("from web import v\n")
    assert cli_run("arch", tmp_path) == 1
    out = capsys.readouterr().out
    assert "domain/m.py:1: domain imports outer layer web" in out
    assert "arch: 2 module(s) checked, 1 violation(s)" in out


def test_arch_passes_a_clean_tree(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "m.py").write_text("")
    assert cli_run("arch", tmp_path) == 0


def test_arch_without_layers_is_an_error_not_a_pass(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n')
    assert cli_run("arch", tmp_path) == 2
    assert "no layers configured" in capsys.readouterr().err


def test_arch_with_layers_matching_nothing_is_an_error(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "other.py").write_text("")
    assert cli_run("arch", tmp_path) == 2
    assert "no module belongs to any configured layer" in capsys.readouterr().err


def test_go_arch_reports_package_without_a_line(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("arch", go_project(tmp_path)) == 1
    assert "m/domain: m/domain imports outer layer m/web" in capsys.readouterr().out


# ---- clean
def test_clean_fails_on_risky_function(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", py_project(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "mod.py:1: g CRAP" in out
    assert "clean: 1 function(s) checked, 1 over CRAP 8" in out


def test_clean_passes_when_functions_are_covered(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", py_project(tmp_path, covered=True)) == 0


def test_clean_without_coverage_exits_2(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n')
    assert cli_run("clean", tmp_path) == 2
    assert (
        "coverage.json not found; produce it with: gauntlet run, or your test runner's coveragepy report"
        in capsys.readouterr().err
    )


def test_clean_with_empty_coverage_is_an_error_not_a_pass(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    py_project(tmp_path)
    (tmp_path / "coverage.json").write_text('{"files": {}}')
    assert cli_run("clean", tmp_path) == 2
    assert "mentions no source file of this project" in capsys.readouterr().err


def test_clean_scope_that_matches_nothing_is_an_error(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", py_project(tmp_path), "--only", "other.py") == 2
    assert "no functions were evaluated" in capsys.readouterr().err


def test_clean_scope_ranges(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path)
    assert cli_run("clean", tmp_path, "--only", "mod.py:1-1") == 1
    assert cli_run("clean", tmp_path, "--only", "mod.py:1-9") == 1


def test_go_clean_fails_on_risky_function(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", go_project(tmp_path)) == 1
    assert "lxd/device/disk.go:28: DiskMount CRAP 342.0 > 8" in capsys.readouterr().out


def test_go_clean_scope_can_exclude_the_offender(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", go_project(tmp_path), "--only", "lxd/device/disk.go:90-99") == 0


def test_go_missing_artifact_says_how_to_make_it(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "go"\n')
    assert cli_run("clean", tmp_path) == 2
    assert (
        capsys.readouterr()
        .err.strip()
        .endswith("cover.out not found; produce it with: gauntlet run, or your test runner's gocover report")
    )


def test_artifacts_can_live_elsewhere(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    root, art = tmp_path / "pilot", tmp_path / "art"
    art.mkdir()
    root.mkdir()
    go_project(root)
    for name in ("cover.out", "imports.txt"):
        (art / name).write_text((root / name).read_text())
        (root / name).unlink()
    assert cli_run("clean", root, "--artifacts", art) == 1
    assert "DiskMount CRAP" in capsys.readouterr().out


# ---- harden
MUTMUT = "p.x_a__mutmut_1: killed\np.x_a__mutmut_2: survived\n"


def test_harden_fails_below_threshold(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n[mutation]\nmin_score = 90\n')
    (tmp_path / "mutmut-results.txt").write_text(MUTMUT)
    assert cli_run("harden", tmp_path) == 1
    out = capsys.readouterr().out
    assert "p.x_a__mutmut_2: survived" in out
    assert "mutation score 50.0% < 90%" in out


def test_harden_passes_at_threshold(tmp_path: Path, capsys: Out, write_policy: Callable[[str], Path]) -> None:
    project(tmp_path, 'language = "python"\n[mutation]\nmin_score = 50\n')
    (tmp_path / "mutmut-results.txt").write_text(MUTMUT)
    pol = write_policy("allow_unstamped = true\nmutation_floor = 50\n")
    assert main(["harden", str(tmp_path), "--policy", str(pol)]) == 0
    assert "mutation score 50.0% >= 50%" in capsys.readouterr().out


def test_harden_never_executes_anything_on_the_host(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n')
    assert cli_run("harden", tmp_path) == 2
    assert capsys.readouterr().err.endswith("(or: gauntlet run)\n")


def test_go_harden_reads_gremlins_json(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    root = go_project(tmp_path)
    muts = [{"type": "X", "status": "LIVED", "line": 3, "column": 1}]
    (root / "mutation.json").write_text(json.dumps({"files": [{"file_name": "a.go", "mutations": muts}]}))
    assert cli_run("harden", root) == 1
    assert "a.go:3:1 X LIVED" in capsys.readouterr().out


def test_go_harden_uses_mutation_dir_for_scope(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    root = go_project(tmp_path, '[go]\nmutation_dir = "lxd/device"\n')
    muts = [{"type": "X", "status": "LIVED", "line": 3, "column": 1}]
    (root / "mutation.json").write_text(json.dumps({"files": [{"file_name": "a.go", "mutations": muts}]}))
    assert cli_run("harden", root, "--only", "lxd/device/a.go:1-9") == 1
    assert "lxd/device/a.go:3:1 X LIVED" in capsys.readouterr().out


# ---- check, exclusions, json
def test_check_runs_arch_clean_and_exclusions(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "m.py").write_text("import web\n")
    assert cli_run("check", tmp_path) == 1
    out = capsys.readouterr().out
    assert "imports outer layer" in out
    assert "clean:" in out
    assert "exclusions:" in out


def test_check_skips_arch_visibly_when_no_layers(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, covered=True)
    assert cli_run("check", tmp_path) == 0
    assert "arch: skipped (no layers configured)" in capsys.readouterr().out


def test_exclusion_comments_are_budgeted(tmp_path: Path, write_policy: Callable[[str], Path], capsys: Out) -> None:
    py_project(tmp_path, covered=True)
    (tmp_path / "mod.py").write_text(BRANCHY + "x = 1  # pragma: no cover\ny = 2  # nosec\n")
    pol = write_policy("allow_unstamped = true\nmax_exclusions = 1\n")
    assert main(["exclusions", str(tmp_path), "--policy", str(pol)]) == 1
    assert "exclusions: 2 comment(s) (budget 1)" in capsys.readouterr().out
    pol = write_policy("allow_unstamped = true\nmax_exclusions = 2\n")
    assert main(["exclusions", str(tmp_path), "--policy", str(pol)]) == 0


def test_config_excludes_fail_unless_the_policy_allows_them(
    tmp_path: Path, write_policy: Callable[[str], Path]
) -> None:
    py_project(tmp_path, covered=True)
    (tmp_path / "pyproject.toml").write_text('[tool.coverage.run]\nomit = ["mod.py"]\n')
    assert main(["exclusions", str(tmp_path), "--policy", str(write_policy("allow_unstamped = true\n"))]) == 1
    allowed = write_policy("allow_unstamped = true\nallow_config_excludes = true\n")
    assert main(["exclusions", str(tmp_path), "--policy", str(allowed)]) == 0


def test_json_output(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    out = tmp_path / "result.json"
    py_project(tmp_path, covered=True)
    assert cli_run("clean", tmp_path, "--json", out) == 0
    (result,) = json.loads(out.read_text())
    assert result["gate"] == "clean"
    assert result["ok"] is True
    assert result["stats"]["functions"] == 1


# ---- policy
def test_repo_cannot_weaken_the_policy(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, 'language = "python"\n[crap]\nmax = 50\n', covered=True)
    assert cli_run("clean", tmp_path) == 2
    assert "weaker than the policy ceiling 8" in capsys.readouterr().err


def test_policy_tightens_the_default(tmp_path: Path, write_policy: Callable[[str], Path], capsys: Out) -> None:
    py_project(tmp_path, covered=True)  # g has complexity 8: covered it scores 8
    pol = write_policy("allow_unstamped = true\ncrap_ceiling = 5\n")
    assert main(["clean", str(tmp_path), "--policy", str(pol)]) == 1
    assert "over CRAP 5" in capsys.readouterr().out


def test_pin_then_edit_is_refused(tmp_path: Path, capsys: Out, write_policy: Callable[[str], Path]) -> None:
    py_project(tmp_path, covered=True)
    pol = write_policy("allow_unstamped = true\n")
    assert main(["pin", str(tmp_path), "--policy", str(pol)]) == 0
    assert main(["clean", str(tmp_path), "--policy", str(pol)]) == 0
    (tmp_path / "gauntlet.toml").write_text('language = "python"\n[crap]\nmax = 7\n')
    assert main(["clean", str(tmp_path), "--policy", str(pol)]) == 2
    assert "changed since it was pinned" in capsys.readouterr().err


def test_pin_creates_a_missing_policy_file(tmp_path: Path) -> None:
    py_project(tmp_path)
    pol = tmp_path / "new" / "policy.toml"
    assert main(["pin", str(tmp_path), "--policy", str(pol)]) == 0
    assert "gauntlet.toml" in pol.read_text()


def test_missing_explicit_policy_is_an_error(tmp_path: Path, capsys: Out) -> None:
    py_project(tmp_path)
    assert main(["clean", str(tmp_path), "--policy", str(tmp_path / "nope.toml")]) == 2
    assert "nope.toml" in capsys.readouterr().err


# ---- provenance
def git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def test_unstamped_artifacts_are_refused_by_default(tmp_path: Path, capsys: Out) -> None:
    py_project(tmp_path, covered=True)
    assert main(["clean", str(tmp_path)]) == 2
    assert "not stamped" in capsys.readouterr().err


def test_stamped_artifacts_pass_and_stale_ones_do_not(tmp_path: Path, capsys: Out) -> None:
    py_project(tmp_path, covered=True)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "x", "--no-gpg-sign")
    assert main(["stamp", str(tmp_path)]) == 0
    assert "stamped coverage.json" in capsys.readouterr().out
    assert main(["clean", str(tmp_path)]) == 0
    (tmp_path / "mod.py").write_text("def g():\n    return 1\n")
    assert main(["clean", str(tmp_path)]) == 2
    assert "stale" in capsys.readouterr().err


def test_stamp_needs_artifacts(tmp_path: Path, capsys: Out) -> None:
    project(tmp_path, 'language = "go"\n')
    git(tmp_path, "init", "-q", "-b", "main")
    assert main(["stamp", str(tmp_path)]) == 2
    assert "no artifacts to stamp" in capsys.readouterr().err


def test_gate_table_is_complete() -> None:
    assert set(cli.GATES) == {"arch", "clean", "harden", "exclusions", "spec", "check"}


# ---- every gate checks exactly its own artifacts
def committed_go_project(root: Path) -> Path:
    go_project(root)
    (root / "mutation.json").write_text(json.dumps({"files": [{"file_name": "a.go", "mutations": []}]}))
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    return root


@pytest.mark.parametrize(
    ("gate", "stamped", "uncovered"),
    [
        ("clean", ["imports.txt", "mutation.json"], "cover.out"),
        ("arch", ["cover.out", "mutation.json"], "imports.txt"),
        ("harden", ["cover.out", "imports.txt"], "mutation.json"),
    ],
)
def test_go_gates_refuse_artifacts_the_manifest_does_not_cover(
    tmp_path: Path, capsys: Out, gate: str, stamped: list[str], uncovered: str
) -> None:
    from gauntlet.provenance import stamp

    root = committed_go_project(tmp_path)
    stamp(root, root, stamped)
    assert main([gate, str(root)]) == 2
    assert f"{uncovered} is not covered by the manifest" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("gate", "missing", "how"),
    [
        ("clean", "cover.out", "gauntlet run, or your test runner's gocover report"),
        ("arch", "imports.txt", "go list -e -f '{{.ImportPath}} {{join .Imports \" \"}}' ./..."),
        ("harden", "mutation.json", "gremlins unleash -o mutation.json ."),
    ],
)
def test_missing_go_artifacts_say_how_to_make_them(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int], gate: str, missing: str, how: str
) -> None:
    root = go_project(tmp_path)
    (root / missing).unlink(missing_ok=True)
    assert cli_run(gate, root) == 2
    assert capsys.readouterr().err.strip() == f"gauntlet: {root / missing} not found; produce it with: {how}"


def test_summaries_are_exact_and_follow_the_findings(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", py_project(tmp_path)) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "clean: 1 function(s) checked, 1 over CRAP 8"
    assert lines[0].startswith("mod.py:1: g CRAP 60.7 > 8 (complexity 8, coverage 6%)")
    assert len(lines) == 2


def test_passing_summaries(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, covered=True)
    assert cli_run("clean", tmp_path) == 0
    assert capsys.readouterr().out == "clean: 1 function(s) checked, 0 over CRAP 8\n"


def test_json_has_every_field(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    out = tmp_path / "result.json"
    assert cli_run("clean", py_project(tmp_path), "--json", out) == 1
    assert out.read_text().startswith('[\n  {\n    "gate": "clean",\n')
    assert out.read_text().endswith("]\n")
    (result,) = json.loads(out.read_text())
    assert result == {
        "gate": "clean",
        "ok": False,
        "summary": "clean: 1 function(s) checked, 1 over CRAP 8",
        "findings": ["mod.py:1: g CRAP 60.7 > 8 (complexity 8, coverage 6%)"],
        "stats": {"functions": 1, "over": 1},
    }


def test_stamp_lists_what_it_stamped(tmp_path: Path, capsys: Out) -> None:
    root = committed_go_project(tmp_path)
    assert main(["stamp", str(root)]) == 0
    assert capsys.readouterr().out == "stamped cover.out, imports.txt, mutation.json\n"


def test_check_fails_when_any_gate_fails(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, covered=True)
    (tmp_path / "mod.py").write_text(BRANCHY + "x = 1  # nosec\n" * 11)
    assert cli_run("clean", tmp_path) == 0
    assert cli_run("exclusions", tmp_path) == 1
    assert cli_run("check", tmp_path) == 1


def test_errors_are_prefixed_and_exact(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n')
    assert cli_run("arch", tmp_path) == 2
    assert capsys.readouterr().err == "gauntlet: no layers configured: add [layers] order to gauntlet.toml\n"


def test_harden_stats_are_reported(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n')
    (tmp_path / "mutmut-results.txt").write_text("a: killed\n" * 19 + "b: survived\n")
    out = tmp_path / "r.json"
    assert cli_run("harden", tmp_path, "--json", out) == 0
    assert json.loads(out.read_text())[0]["stats"] == {"score": 95.0, "caught": 19, "total": 20}


def test_source_defaults_to_root_and_can_differ(tmp_path: Path, capsys: Out) -> None:
    src, pilot = tmp_path / "src", tmp_path / "pilot"
    src.mkdir()
    pilot.mkdir()
    (src / "a.py").write_text("x = 1\n")
    git(src, "init", "-q", "-b", "main")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "x", "--no-gpg-sign")
    go_project(pilot)
    assert main(["stamp", str(pilot), "--source", str(src)]) == 0
    capsys.readouterr()
    assert main(["clean", str(pilot), "--source", str(src)]) == 1  # verified, then found DiskMount
    (src / "a.py").write_text("x = 2\n")
    assert main(["clean", str(pilot), "--source", str(src)]) == 2
    assert "stale" in capsys.readouterr().err


# ---- run (sandboxed pipeline) and report
class RunSandbox:
    """Stands in for Workshop: 'runs' the python steps by writing what they would have produced."""

    def __init__(self, project: Path, covered: bool = True) -> None:
        self.project, self.covered, self.removed = project, covered, False

    def ensure(self) -> None: ...

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        out = self.project / ".gauntlet-out"
        if "pytest" in argv:
            cov = {"files": {"mod.py": {"executed_lines": list(range(1, 17)), "missing_lines": []}}}
            if not self.covered:
                cov = {"files": {"mod.py": {"executed_lines": [1], "missing_lines": list(range(2, 17))}}}
            (out / "coverage.json").write_text(json.dumps(cov))
        if list(argv[-3:]) == ["results", "--all", "true"]:
            return ExecResult(0, "p.x: killed\n" * 9 + "p.y: survived\n", "")
        return ExecResult(0, "", "")

    def remove(self) -> None:
        self.removed = True


def sandbox_factory(covered: bool = True) -> Callable[[Path, Config, Policy], RunSandbox]:
    return lambda project, cfg, policy: RunSandbox(project, covered)  # noqa: ARG005


def committed_py_project(root: Path, toml: str = 'language = "python"\n') -> Path:
    project(root, toml)
    (root / "mod.py").write_text(BRANCHY)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    return root


def test_run_produces_artifacts_in_the_sandbox_then_evaluates_every_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["run", str(root)]) == 0
    out = capsys.readouterr().out
    assert "produced coverage.json, mutmut-results.txt" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "exclusions:" in out
    assert "mutation score 90.0% >= 90%" in out
    assert (root / ".gauntlet" / "gauntlet-manifest.json").exists()


def test_run_fails_when_a_gate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory(covered=False))
    assert main(["run", str(root)]) == 1


def test_run_honours_out_and_ignores_stale_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path / "repo") if (tmp_path / "repo").mkdir() is None else tmp_path
    (root / "coverage.json").write_text('{"files": {}}')  # stale junk next to the sources must not matter
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    out = tmp_path / "elsewhere"
    assert main(["run", str(root), "--out", str(out)]) == 0
    assert (out / "coverage.json").exists()
    capsys.readouterr()


def test_report_is_written_for_any_gate(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, covered=True)
    report = tmp_path / "EVIDENCE.md"
    assert cli_run("clean", tmp_path, "--report", report) == 0
    text = report.read_text()
    assert text.startswith("# Evidence report")
    assert "| clean | PASS |" in text
    assert "Source fingerprint: `unavailable" in text
    assert "gauntlet clean" in text


def test_report_carries_the_real_fingerprint_in_a_repository(tmp_path: Path) -> None:
    from gauntlet.provenance import fingerprint

    root = committed_py_project(tmp_path)
    (root / "coverage.json").write_text(
        json.dumps({"files": {"mod.py": {"executed_lines": list(range(1, 17)), "missing_lines": []}}})
    )
    assert main(["stamp", str(root)]) == 0
    assert main(["clean", str(root), "--report", str(root / "E.md")]) == 0
    assert fingerprint(root, ("E.md", "gauntlet-manifest.json")) in (root / "E.md").read_text()


# ---- spec and diagram
FEATURE = "Feature: f\n  @test(mod.py::g)\n  Scenario: s\n    When x\n    Then y\n"


def test_spec_gate_passes_a_traceable_spec(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path)
    (tmp_path / "spec.feature").write_text(FEATURE)
    assert cli_run("spec", tmp_path) == 0
    assert capsys.readouterr().out == "spec: 1 scenario(s), 0 problem(s)\n"


def test_spec_gate_lists_every_problem(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path)
    (tmp_path / "other.feature").write_text("Feature: f\n  Scenario: s\n    Given a\n")
    assert cli_run("spec", tmp_path, "--feature", tmp_path / "other.feature") == 1
    out = capsys.readouterr().out.splitlines()
    assert "'s' has no When" in out
    assert out[-1] == "spec: 1 scenario(s), 3 problem(s)"


def test_spec_gate_needs_the_file(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path)
    assert cli_run("spec", tmp_path) == 2
    assert "spec.feature" in capsys.readouterr().err


def test_diagram_prints_mermaid_for_python(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "web").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "web" / "v.py").write_text("import domain.m\n")
    (tmp_path / "domain" / "m.py").write_text("")
    assert cli_run("diagram", tmp_path) == 0
    assert capsys.readouterr().out == 'flowchart TD\n  L0["web"]\n  L1["domain"]\n  L0 --> L1\n'


def test_diagram_marks_violations_for_go(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("diagram", go_project(tmp_path)) == 0
    assert "L1 -.->|violation| L0" in capsys.readouterr().out


def test_diagram_needs_layers(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "python"\n')
    assert cli_run("diagram", tmp_path) == 2
    assert "no layers configured" in capsys.readouterr().err


# ---- loop
AGENT_POLICY = 'allow_unstamped = true\nagent_command = ["agent", "-p"]\nagent_env = ["TOKEN"]\nmax_rounds = 2\n'
LOOP_SPEC = "Feature: f\n  @test(test_mod.py::test_g)\n  Scenario: s\n    When x\n    Then y\n"


class AgentBox:
    """Stands in for the agent sandbox: acts on the workspace like a (very small) coding agent would."""

    def __init__(self, project: Path, script: Callable[[str, Path], ExecResult]) -> None:
        self.project, self.script, self.prompts = project, script, []

    prompts: list[str]

    def ensure(self) -> None: ...

    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        self.prompts.append(argv[-1])
        return self.script(argv[-1], self.project)

    def remove(self) -> None: ...


class LoopGates(RunSandbox):
    """Gate sandbox whose coverage depends on whether the workspace got the 'fix'."""

    def __init__(self, project: Path) -> None:
        super().__init__(project, covered=(project / "fixed.txt").exists())


def agent_script(prompt: str, project: Path) -> ExecResult:
    if "You are the Specifier" in prompt:
        (project / "spec.feature").write_text(LOOP_SPEC)
    elif "You are the Coder" in prompt:
        (project / "test_mod.py").write_text("def test_g():\n    assert True\n")
        (project / "mod.py").write_text(BRANCHY)
    elif "You are the Fixer" in prompt:
        (project / "fixed.txt").write_text("fixed")
    return ExecResult(0, "", "")


def loop_gates(project: Path, cfg: Config, policy: Policy) -> LoopGates:  # noqa: ARG001
    return LoopGates(project)


def loop_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_policy: Callable[[str], Path],
    script: Callable[[str, Path], ExecResult] = agent_script,
    policy_text: str = AGENT_POLICY,
) -> tuple[Path, Path, list[AgentBox]]:
    root = committed_py_project(tmp_path / "repo") if (tmp_path / "repo").mkdir() is None else tmp_path
    boxes: list[AgentBox] = []

    def make_agent(workspace: Path, cfg: Config, policy: Policy) -> AgentBox:
        boxes.append(AgentBox(workspace, script))
        return boxes[-1]

    monkeypatch.setattr(cli, "MAKE_AGENT_SANDBOX", make_agent)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", loop_gates)
    return root, write_policy(policy_text), boxes


def test_loop_needs_an_agent_in_the_policy(tmp_path: Path, capsys: Out, write_policy: Callable[[str], Path]) -> None:
    root = committed_py_project(tmp_path)
    pol = write_policy("allow_unstamped = true\n")
    assert main(["loop", str(root), "--requirement", "x", "--policy", str(pol)]) == 2
    assert "no agent configured" in capsys.readouterr().err


def test_loop_needs_a_requirement_or_a_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy)
    assert main(["loop", str(root), "--policy", str(pol)]) == 2
    assert "--requirement" in capsys.readouterr().err


def test_loop_without_an_approved_spec_stops_after_the_specifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, boxes = loop_setup(tmp_path, monkeypatch, write_policy)
    assert main(["loop", str(root), "--requirement", "limit things", "--policy", str(pol)]) == 3
    out = root / ".gauntlet-loop"
    assert (out / "spec.feature").read_text() == LOOP_SPEC
    assert "rerun with --spec" in capsys.readouterr().out
    assert len(boxes[0].prompts) == 1 and "limit things" in boxes[0].prompts[0]
    assert not (root / "spec.feature").exists()  # the real tree is untouched


def test_loop_with_an_approved_spec_implements_and_hands_back_a_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, boxes = loop_setup(tmp_path, monkeypatch, write_policy)
    spec_file = tmp_path / "approved.feature"
    spec_file.write_text(LOOP_SPEC)
    # first evaluation fails (no 'fixed.txt'), the fixer adds it, the second passes
    code = main(["loop", str(root), "--spec", str(spec_file), "--policy", str(pol)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert [("Coder" in p, "Fixer" in p) for p in boxes[0].prompts] == [(True, False), (False, True)]
    loop_dir = root / ".gauntlet-loop"
    patch_text = (loop_dir / "loop.patch").read_text()
    assert "test_mod.py" in patch_text and "fixed.txt" in patch_text
    assert (loop_dir / "EVIDENCE.md").read_text().startswith("# Evidence report")
    assert not (root / "test_mod.py").exists()  # nothing landed in the real tree
    assert "fixer rounds: 1" in out


def test_loop_reports_failure_and_flags_control_file_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    def sneaky(prompt: str, project: Path) -> ExecResult:
        if "You are the Coder" in prompt:
            (project / "test_mod.py").write_text("def test_g(): pass\n")
            (project / "mod.py").write_text(BRANCHY)
            (project / "gauntlet.toml").write_text('language = "python"\n[crap]\nmax = 99\n')
        return ExecResult(0, "", "")  # the fixer never fixes anything

    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy, sneaky)
    spec_file = tmp_path / "approved.feature"
    spec_file.write_text(LOOP_SPEC)
    assert main(["loop", str(root), "--spec", str(spec_file), "--policy", str(pol)]) == 1
    out = capsys.readouterr().out
    assert "fixer rounds: 2" in out
    assert "touches control files: gauntlet.toml" in out
    assert "over CRAP 8" in out  # the agent's own gauntlet.toml edit did not relax the limit


def test_loop_agent_failure_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy, lambda p, d: ExecResult(7, "", "agent crashed"))
    assert main(["loop", str(root), "--requirement", "x", "--policy", str(pol)]) == 2
    assert "specifier failed (exit 7): agent crashed" in capsys.readouterr().err


def test_loop_prints_exact_summary_and_writes_a_complete_evidence_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    import hashlib

    root, pol, _ = loop_setup(tmp_path, monkeypatch, write_policy)
    spec_file = tmp_path / "approved.feature"
    spec_file.write_text(LOOP_SPEC)
    assert main(["loop", str(root), "--spec", str(spec_file), "--policy", str(pol)]) == 0
    out = capsys.readouterr().out.splitlines()
    loop_dir = root / ".gauntlet-loop"
    assert out[-1] == f"fixer rounds: 1; patch: {loop_dir / 'loop.patch'}; evidence: {loop_dir / 'EVIDENCE.md'}"
    text = (loop_dir / "EVIDENCE.md").read_text()
    assert "- Language: python" in text
    assert f"`{hashlib.sha256((root / 'gauntlet.toml').read_bytes()).hexdigest()}`" in text
    assert re.search(r"Source fingerprint: `[0-9a-f]{64}`", text)
    assert re.search(r"Generated \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00 by gauntlet", text)
    assert f"gauntlet loop {root} --spec {spec_file}" in text
    assert (loop_dir / "artifacts" / "gauntlet-manifest.json").exists()


def test_evidence_report_from_a_gate_has_the_real_language_hash_and_time(
    tmp_path: Path, cli_run: Callable[..., int]
) -> None:
    import hashlib

    py_project(tmp_path, covered=True)
    report = tmp_path / "E.md"
    assert cli_run("clean", tmp_path, "--report", report) == 0
    text = report.read_text()
    assert "- Language: python" in text
    assert hashlib.sha256((tmp_path / "gauntlet.toml").read_bytes()).hexdigest() in text
    assert re.search(r"Generated \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00 by", text)


def test_gates_default_to_the_results_of_the_last_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory())
    assert main(["run", str(root)]) == 0
    capsys.readouterr()
    assert main(["clean", str(root)]) == 0  # finds .gauntlet/ by itself: stamped, so it verifies
    (root / "mod.py").write_text("def g():\n    return 2\n")
    assert main(["clean", str(root)]) == 2
    assert "stale" in capsys.readouterr().err


def test_stamp_never_blesses_the_results_of_an_old_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = committed_py_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", sandbox_factory(covered=False))
    assert main(["run", str(root)]) == 1  # leaves .gauntlet/ with uncovered results
    capsys.readouterr()
    covered = {"mod.py": {"executed_lines": list(range(1, 17)), "missing_lines": []}}
    (root / "coverage.json").write_text(json.dumps({"files": covered}))  # fresh artifacts next to the sources
    assert main(["stamp", str(root)]) == 0
    assert "stamped coverage.json" in capsys.readouterr().out
    assert (root / "gauntlet-manifest.json").exists()
    assert main(["clean", str(root), "--artifacts", str(root)]) == 0  # the fresh ones, not the old run's


# ---- Rust: lcov with absolute container paths
class RustSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if "--lcov" in argv:
            lcov = "SF:/project/src/lib.rs\nDA:1,1\nDA:2,1\nend_of_record\n"
            (self.project / ".gauntlet-out" / "lcov.info").write_text(lcov)
        return ExecResult(0, "", "")


def test_run_checks_rust_coverage_from_absolute_container_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    lax = write_policy("allow_skipped_gates = true\n")
    root = project(tmp_path, 'language = "rust"\n')
    (root / "src").mkdir()
    (root / "src" / "lib.rs").write_text("pub fn f(x: i32) -> i32 {\n    x + 1\n}\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: RustSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root), "--policy", str(lax)]) == 0
    out = capsys.readouterr().out
    assert "produced lcov.info" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "harden: SKIPPED, no mutation tool is wired for rust yet" in out


# ---- JavaScript: coverage gates work, harden is visibly skipped
JS_SOURCE = "function f(x) {\n  return x + 1;\n}\nmodule.exports = { f };\n"


class JsSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if "c8@10.1.3" in argv:
            (self.project / ".gauntlet-out" / "lcov.info").write_text("SF:index.js\nDA:1,1\nDA:2,1\nend_of_record\n")
        return ExecResult(0, "", "")


def committed_js_project(root: Path, toml: str = 'language = "javascript"\n') -> Path:
    project(root, toml)
    (root / "index.js").write_text(JS_SOURCE)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    return root


def test_run_checks_javascript_coverage_and_says_harden_was_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    lax = write_policy("allow_skipped_gates = true\n")
    root = committed_js_project(tmp_path)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: JsSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root)]) == 1  # a skipped gate is a failure unless the operator's policy accepts it
    assert "allow_skipped_gates = true" in capsys.readouterr().out
    assert main(["run", str(root), "--policy", str(lax)]) == 0
    out = capsys.readouterr().out
    assert "produced lcov.info" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "harden: SKIPPED, no mutation tool is wired for javascript yet" in out


def test_harden_asked_for_directly_is_an_error_where_no_tool_is_wired(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    assert cli_run("harden", project(tmp_path, 'language = "javascript"\n')) == 2
    assert "harden is not available for javascript yet" in capsys.readouterr().err


def test_arch_with_layers_is_an_error_where_no_import_reader_exists(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    root = project(tmp_path, 'language = "javascript"\n[layers]\norder = ["a", "b"]\n')
    assert cli_run("arch", root) == 2
    assert "arch has no import reader for javascript yet" in capsys.readouterr().err


# ---- C#: coverage gates work, harden is visibly skipped
CS_SOURCE = "namespace Demo;\npublic static class A\n{\n    public static int F(int x)\n    {\n        return x + 1;\n    }\n}\n"
CS_COBERTURA = (
    "<coverage><sources><source>/</source></sources>"  # as coverlet writes it in the container
    '<packages><package><classes><class filename="project/src/A.cs"><lines>'
    '<line number="6" hits="1"/></lines></class></classes></package></packages></coverage>'
)


class CsSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if argv[0] == "sh":  # the step that moves the report out of its results/<guid>/ directory
            (self.project / ".gauntlet-out" / "coverage.cobertura.xml").write_text(CS_COBERTURA)
        return ExecResult(0, "", "")


def test_run_checks_csharp_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root = project(tmp_path, 'language = "csharp"\n')
    (root / "src").mkdir()
    (root / "src" / "A.cs").write_text(CS_SOURCE)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: CsSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root), "--policy", str(write_policy("allow_skipped_gates = true\n"))]) == 0
    out = capsys.readouterr().out
    assert "produced coverage.cobertura.xml" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "harden: SKIPPED, no mutation tool is wired for csharp yet" in out


# ---- Java: JaCoCo XML, harden skipped
JAVA_SOURCE = "package com.x;\npublic class A {\n  int f(int x) {\n    return x + 1;\n  }\n}\n"
JACOCO_XML = (
    '<report name="r"><package name="com/x"><sourcefile name="A.java">'
    '<line nr="4" mi="0" ci="1" mb="0" cb="0"/></sourcefile></package></report>'
)


class JavaSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if argv[0] == "cp":
            (self.project / ".gauntlet-out" / "jacoco.xml").write_text(JACOCO_XML)
        return ExecResult(0, "", "")


def test_run_checks_java_coverage_and_says_harden_was_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    root = project(tmp_path, 'language = "java"\n')
    (root / "src/main/java/com/x").mkdir(parents=True)
    (root / "src/main/java/com/x/A.java").write_text(JAVA_SOURCE)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x", "--no-gpg-sign")
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: JavaSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    lax = write_policy("allow_skipped_gates = true\n")
    assert main(["run", str(root), "--policy", str(lax)]) == 0
    out = capsys.readouterr().out
    assert "produced jacoco.xml" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "harden: SKIPPED, no mutation tool is wired for java yet" in out


# ---- C and C++: coverage gates work, harden is visibly skipped
class CppSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if "gcovr" in argv:
            (self.project / ".gauntlet-out" / "lcov.info").write_text(
                "SF:/project/a.c\nDA:1,1\nDA:2,1\nend_of_record\n"
            )
        return ExecResult(0, "", "")


def test_run_checks_cpp_coverage_and_says_harden_was_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out, write_policy: Callable[[str], Path]
) -> None:
    lax = write_policy("allow_skipped_gates = true\n")
    project(tmp_path, 'language = "cpp"\n')
    (tmp_path / "a.c").write_text("int f(int x) {\n  return x + 1;\n}\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "x", "--no-gpg-sign")):
        git(tmp_path, *args)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: CppSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(tmp_path)]) == 1  # a skipped gate fails unless the operator's policy accepts it
    assert main(["run", str(tmp_path), "--policy", str(lax)]) == 0
    out = capsys.readouterr().out
    assert "produced lcov.info" in out
    assert "clean: 1 function(s) checked, 0 over CRAP 8" in out
    assert "harden: SKIPPED, no mutation tool is wired for cpp yet" in out


# ---- Dart: the same, with the unreadable-file rule visible end to end
DART_SOURCE = "int f(int x) {\n  return x + 1;\n}\n"


class DartSandbox(RunSandbox):
    def exec(self, argv: Sequence[str], env: Mapping[str, str | None] | None = None, timeout: int = 600) -> ExecResult:
        if "coverage:format_coverage" in argv:
            text = "SF:/project/lib/a.dart\nDA:1,1\nDA:2,1\nend_of_record\n"
            (self.project / ".gauntlet-out" / "lcov.info").write_text(text)
        return ExecResult(0, "", "")


def test_run_checks_dart_coverage_and_names_code_the_reader_could_not_see(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Out
) -> None:
    root = project(tmp_path, 'language = "dart"\n')
    (root / "lib").mkdir()
    (root / "lib" / "a.dart").write_text(DART_SOURCE)
    (root / "lib" / "b.dart").write_text("int one() => 1;\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "x", "--no-gpg-sign")):
        git(root, *args)
    monkeypatch.setattr(cli, "MAKE_SANDBOX", lambda project, cfg, policy: DartSandbox(project))  # type: ignore[misc]  # noqa: ARG005
    assert main(["run", str(root)]) == 1
    out = capsys.readouterr().out
    assert "produced lcov.info" in out
    assert "lib/b.dart:1: (unread code) CRAP inf > 8 (complexity 0, coverage 0%)" in out
    assert "harden: SKIPPED, no mutation tool is wired for dart yet" in out
