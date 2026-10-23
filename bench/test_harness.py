import json
import subprocess
from pathlib import Path

import pytest
from harness import Case, assemble, checkers, coverage_pct, load_cases, outcome, report, score, validity


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_cases_are_read_from_every_task_in_order(tmp_path: Path) -> None:
    for task, case, kind in [("b", "c1", "planted"), ("a", "ref", "reference"), ("a", "g1", "gaming")]:
        meta = {"kind": kind, "bug": "off-by-one", "base": "reference"}
        write(tmp_path / task / "cases" / case / "meta.json", json.dumps(meta))
    found = load_cases(tmp_path)
    assert [(c.task, c.name, c.kind) for c in found] == [
        ("a", "g1", "gaming"),
        ("a", "ref", "reference"),
        ("b", "c1", "planted"),
    ]
    assert found[0].files == tmp_path / "a" / "cases" / "g1" / "files"
    assert (found[0].bug, found[0].base) == ("off-by-one", "reference")


def test_an_unknown_kind_is_refused(tmp_path: Path) -> None:
    write(tmp_path / "a" / "cases" / "x" / "meta.json", json.dumps({"kind": "lucky"}))
    with pytest.raises(ValueError, match="unknown kind 'lucky'"):
        load_cases(tmp_path)


def test_assemble_lays_template_then_task_repo_then_case_and_commits(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks"
    write(tmp_path / "template" / "pyproject.toml", "shared\n")
    write(tmp_path / "template" / "README.md", "template\n")
    write(tasks / "a" / "repo" / "src" / "m.py", "stub\n")
    write(tasks / "a" / "repo" / "README.md", "task\n")
    write(tasks / "a" / "cases" / "c" / "files" / "src" / "m.py", "real\n")
    write(tasks / "a" / "cases" / "ref" / "files" / "tests" / "test_m.py", "visible\n")
    write(tasks / "a" / "cases" / "ref" / "files" / "src" / "m.py", "correct\n")
    case = Case("a", "c", "planted", "", tasks / "a" / "cases" / "c" / "files", "ref")
    dest = tmp_path / "work"
    assemble(tasks, case, dest)
    assert (dest / "src" / "m.py").read_text() == "real\n"
    assert (dest / "README.md").read_text() == "task\n"
    assert (dest / "pyproject.toml").read_text() == "shared\n"
    assert (dest / "tests" / "test_m.py").read_text() == "visible\n"  # from the base case
    status = subprocess.run(
        ["git", "-C", str(dest), "status", "--porcelain"], capture_output=True, text=True, check=True
    )
    assert status.stdout == ""


def test_outcome_separates_failed_tests_errors_and_failed_gates() -> None:
    results = [{"gate": "clean", "ok": True}, {"gate": "harden", "ok": False, "stats": {"score": 84.4}}]
    assert outcome(1, "", results) == {
        "gauntlet_fail": True, "tests_failed": False, "gates": ["harden"], "error": "", "mutation": 84.4
    }  # fmt: skip
    tests = outcome(2, "gauntlet: step 'tests' failed (exit 1): boom\n", [])
    assert tests == {"gauntlet_fail": True, "tests_failed": True, "gates": [], "error": "", "mutation": None}
    other = outcome(2, "gauntlet: no functions were evaluated\n", [])
    assert other["error"] == "gauntlet: no functions were evaluated" and not other["tests_failed"]
    assert outcome(0, "", [{"gate": "clean", "ok": True}])["gauntlet_fail"] is False


def test_coverage_is_the_report_total_or_none(tmp_path: Path) -> None:
    write(tmp_path / "coverage.json", json.dumps({"totals": {"percent_covered": 87.5}}))
    assert coverage_pct(tmp_path / "coverage.json") == 87.5
    assert coverage_pct(tmp_path / "missing.json") is None


def row(kind: str, hidden_pass: bool, **kw: object) -> dict[str, object]:
    base: dict[str, object] = {"task": "t", "case": "c", "kind": kind, "bug": "", "hidden_pass": hidden_pass}
    base.update({"tests_failed": False, "coverage": 100.0, "gauntlet_fail": False, "gates": [], "error": ""})
    base.update(kw)
    return base


def test_checkers_fail_a_patch_from_their_own_evidence() -> None:
    assert checkers(row("planted", False, tests_failed=True)) == {"baseline": True, "coverage": True, "gauntlet": False}
    assert checkers(row("planted", False, coverage=79.9)) == {"baseline": False, "coverage": True, "gauntlet": False}
    assert checkers(row("planted", False, coverage=None, gauntlet_fail=True))["coverage"] is True
    assert checkers(row("planted", False, gauntlet_fail=True)) == {
        "baseline": False,
        "coverage": False,
        "gauntlet": True,
    }


def test_score_counts_catches_where_a_patch_should_fail_and_alarms_where_it_should_pass() -> None:
    rows = [
        row("planted", False, gauntlet_fail=True),
        row("planted", False),
        row("reference", True, gauntlet_fail=True),
        row("reference", True),
        row("weak-tests", True, gauntlet_fail=True),  # correct code, tests too thin: failing it is right
    ]
    scores = score(rows)
    assert scores["planted"]["gauntlet"] == {"caught": 1, "should_fail": 2, "alarms": 0, "should_pass": 0}
    assert scores["reference"]["gauntlet"] == {"caught": 0, "should_fail": 0, "alarms": 1, "should_pass": 2}
    assert scores["weak-tests"]["gauntlet"] == {"caught": 1, "should_fail": 1, "alarms": 0, "should_pass": 0}
    assert scores["all"]["gauntlet"] == {"caught": 2, "should_fail": 3, "alarms": 1, "should_pass": 2}


def test_invalid_cases_are_named() -> None:
    rows = [
        row("planted", True, case="escaped"),  # the planted bug does not break the hidden tests
        row("planted", False, case="loud", tests_failed=True),  # the visible tests already catch it
        row("reference", False, case="wrong"),  # the reference solution fails the hidden tests
        row("planted", False, case="fine"),
        row("gaming", False, case="g"),
        row("natural", False, case="n", tests_failed=True),
        row("weak-tests", False, case="broken"),  # weak tests must sit on correct code
    ]
    assert validity(rows) == [
        "t/escaped: planted bug passes the hidden tests",
        "t/loud: planted bug fails the visible tests",
        "t/wrong: reference fails the hidden tests",
        "t/broken: weak-tests code fails the hidden tests",
    ]


def test_report_is_a_markdown_table_with_invalid_cases_left_out() -> None:
    rows = [row("planted", False, gauntlet_fail=True, gates=["harden"]), row("planted", True, case="escaped")]
    text = report(rows)
    assert "| planted | baseline | 0/1 | - |" in text
    assert "| planted | gauntlet | 1/1 | - |" in text
    assert "Invalid cases (left out): t/escaped: planted bug passes the hidden tests" in text
    assert "| harden | 1 |" in text
    assert "| t/c | planted | fail | fail | - | 100.0 |" in text  # per case: expected, gauntlet, mutation, coverage
