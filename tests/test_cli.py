import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from helpers import (
    BRANCHY,
    Out,
    committed_py_project,
    git,
    project,
    py_project,
)

from gauntlet import cli
from gauntlet.cli import main


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
    assert "cannot read fakecov report" in capsys.readouterr().err


# ---- arch
def test_arch_fails_on_outward_import(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "web").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "web" / "v.py").write_text("")
    (tmp_path / "domain" / "m.py").write_text("from web import v\n")
    assert cli_run("arch", tmp_path) == 1
    out = capsys.readouterr().out
    assert "domain/m.py:1: domain imports outer layer web" in out
    assert "arch: 2 module(s) checked, 1 violation(s)" in out


def test_arch_checks_every_root_and_enforces_forbid_rules(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    toml = 'language = "fake"\n[layers]\norder = ["web", "domain"]\nroots = ["a", "b"]\nforbid = ["web -> domain"]\n'
    project(tmp_path, toml)
    (tmp_path / "a" / "web").mkdir(parents=True)
    (tmp_path / "b" / "domain").mkdir(parents=True)
    (tmp_path / "a" / "web" / "v.py").write_text("import domain.m\n")
    (tmp_path / "b" / "domain" / "m.py").write_text("")
    assert cli_run("arch", tmp_path) == 1
    out = capsys.readouterr().out
    assert "web/v.py:1: web.v imports forbidden domain" in out
    assert "arch: 2 module(s) checked, 1 violation(s)" in out


def test_arch_passes_a_clean_tree(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "m.py").write_text("")
    assert cli_run("arch", tmp_path) == 0


def test_arch_without_layers_is_an_error_not_a_pass(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n')
    assert cli_run("arch", tmp_path) == 2
    assert "no layers configured" in capsys.readouterr().err


def test_arch_with_layers_matching_nothing_is_an_error(
    tmp_path: Path, capsys: Out, cli_run: Callable[..., int]
) -> None:
    project(tmp_path, 'language = "fake"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "other.py").write_text("")
    assert cli_run("arch", tmp_path) == 2
    assert "no module under . belongs to any configured layer" in capsys.readouterr().err


# ---- clean
def test_clean_fails_on_risky_function(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", py_project(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "mod.py:1: g CRAP" in out
    assert "clean: 1 function(s) checked, 1 over CRAP 8" in out


def test_clean_passes_when_functions_are_covered(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    assert cli_run("clean", py_project(tmp_path, covered=True)) == 0


def test_clean_without_coverage_exits_2(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n')
    assert cli_run("clean", tmp_path) == 2
    assert (
        "coverage.json not found; produce it with: gauntlet run, or your test runner's fakecov report"
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


def test_artifacts_can_live_elsewhere(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    root, art = tmp_path / "pilot", tmp_path / "art"
    art.mkdir()
    root.mkdir()
    py_project(root)
    (art / "coverage.json").write_text((root / "coverage.json").read_text())
    (root / "coverage.json").unlink()
    assert cli_run("clean", root, "--artifacts", art) == 1
    assert "g CRAP" in capsys.readouterr().out


# ---- harden
MUTMUT = "p.x_a__mutmut_1: killed\np.x_a__mutmut_2: survived\n"


def test_harden_fails_below_threshold(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n[mutation]\nmin_score = 90\n')
    (tmp_path / "mutmut-results.txt").write_text(MUTMUT)
    assert cli_run("harden", tmp_path) == 1
    out = capsys.readouterr().out
    assert "p.x_a__mutmut_2: survived" in out
    assert "mutation score 50.0% < 90%" in out


def test_harden_passes_at_threshold(tmp_path: Path, capsys: Out, write_policy: Callable[[str], Path]) -> None:
    project(tmp_path, 'language = "fake"\n[mutation]\nmin_score = 50\n')
    (tmp_path / "mutmut-results.txt").write_text(MUTMUT)
    pol = write_policy("allow_unstamped = true\nmutation_floor = 50\n")
    assert main(["harden", str(tmp_path), "--policy", str(pol)]) == 0
    assert "mutation score 50.0% >= 50%" in capsys.readouterr().out


def test_harden_never_executes_anything_on_the_host(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n')
    assert cli_run("harden", tmp_path) == 2
    assert capsys.readouterr().err.endswith("(or: gauntlet run)\n")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ValueError("Expecting value"), "gauntlet: malformed input: Expecting value\n"),
        (TypeError("bad"), "gauntlet: malformed input: bad\n"),
        (KeyError("files"), "gauntlet: malformed input, missing 'files'\n"),
    ],
)
def test_an_artifact_the_reader_chokes_on_is_named_malformed_input(
    monkeypatch: pytest.MonkeyPatch, capsys: Out, error: Exception, message: str
) -> None:
    def boom(args: object) -> int:
        raise error

    monkeypatch.setattr(cli, "_dispatch", boom)
    assert main(["clean"]) == 2
    assert capsys.readouterr().err == message


# ---- check, exclusions, json
def test_check_runs_arch_clean_and_exclusions(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, 'language = "fake"\n[layers]\norder = ["web", "domain"]\n')
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
    (tmp_path / "excludes.txt").write_text("coverage omit mod.py\n")
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
    py_project(tmp_path, 'language = "fake"\n[crap]\nmax = 50\n', covered=True)
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
    (tmp_path / "gauntlet.toml").write_text('language = "fake"\n[crap]\nmax = 7\n')
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
    project(tmp_path, 'language = "fake"\n')
    git(tmp_path, "init", "-q", "-b", "main")
    assert main(["stamp", str(tmp_path)]) == 2
    assert "no artifacts to stamp" in capsys.readouterr().err


def test_gate_table_is_complete() -> None:
    assert set(cli.GATES) == {"arch", "clean", "harden", "exclusions", "spec", "check"}


# ---- every gate checks exactly its own artifacts
@pytest.mark.parametrize(
    ("gate", "stamped", "uncovered"),
    [("clean", ["mutmut-results.txt"], "coverage.json"), ("harden", ["coverage.json"], "mutmut-results.txt")],
)
def test_gates_refuse_artifacts_the_manifest_does_not_cover(
    tmp_path: Path, capsys: Out, gate: str, stamped: list[str], uncovered: str
) -> None:
    from gauntlet.provenance import stamp

    root = committed_py_project(tmp_path)
    (root / "coverage.json").write_text('{"files": {}}')
    (root / "mutmut-results.txt").write_text(MUTMUT)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "y", "--no-gpg-sign")
    stamp(root, root, stamped)
    assert main([gate, str(root)]) == 2
    assert f"{uncovered} is not covered by the manifest" in capsys.readouterr().err


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
    root = committed_py_project(tmp_path)
    (root / "coverage.json").write_text('{"files": {}}')
    (root / "mutmut-results.txt").write_text(MUTMUT)
    assert main(["stamp", str(root)]) == 0
    assert capsys.readouterr().out == "stamped coverage.json, mutmut-results.txt\n"


def test_check_fails_when_any_gate_fails(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    py_project(tmp_path, covered=True)
    (tmp_path / "mod.py").write_text(BRANCHY + "x = 1  # nosec\n" * 11)
    assert cli_run("clean", tmp_path) == 0
    assert cli_run("exclusions", tmp_path) == 1
    assert cli_run("check", tmp_path) == 1


def test_errors_are_prefixed_and_exact(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n')
    assert cli_run("arch", tmp_path) == 2
    assert capsys.readouterr().err == "gauntlet: no layers configured: add [layers] order to gauntlet.toml\n"


def test_harden_stats_are_reported(tmp_path: Path, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n')
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
    py_project(pilot)
    assert main(["stamp", str(pilot), "--source", str(src)]) == 0
    capsys.readouterr()
    assert main(["clean", str(pilot), "--source", str(src)]) == 1  # verified, then found g
    (src / "a.py").write_text("x = 2\n")
    assert main(["clean", str(pilot), "--source", str(src)]) == 2
    assert "stale" in capsys.readouterr().err


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
    project(tmp_path, 'language = "fake"\n[layers]\norder = ["web", "domain"]\n')
    (tmp_path / "web").mkdir()
    (tmp_path / "domain").mkdir()
    (tmp_path / "web" / "v.py").write_text("import domain.m\n")
    (tmp_path / "domain" / "m.py").write_text("")
    assert cli_run("diagram", tmp_path) == 0
    assert capsys.readouterr().out == 'flowchart TD\n  L0["web"]\n  L1["domain"]\n  L0 --> L1\n'


def test_diagram_needs_layers(tmp_path: Path, capsys: Out, cli_run: Callable[..., int]) -> None:
    project(tmp_path, 'language = "fake"\n')
    assert cli_run("diagram", tmp_path) == 2
    assert "no layers configured" in capsys.readouterr().err


def test_evidence_report_from_a_gate_has_the_real_language_hash_and_time(
    tmp_path: Path, cli_run: Callable[..., int]
) -> None:
    import hashlib

    py_project(tmp_path, covered=True)
    report = tmp_path / "E.md"
    assert cli_run("clean", tmp_path, "--report", report) == 0
    text = report.read_text()
    assert "- Language: fake" in text
    assert hashlib.sha256((tmp_path / "gauntlet.toml").read_bytes()).hexdigest() in text
    assert re.search(r"Generated \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00 by", text)
