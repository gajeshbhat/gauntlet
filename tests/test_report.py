from gauntlet.policy import Policy
from gauntlet.report import render
from gauntlet.results import GateResult

PASS = GateResult("clean", True, "clean: 5 function(s) checked, 0 over CRAP 8", (), {"functions": 5})
FAIL = GateResult("arch", False, "arch: 3 module(s) checked, 1 violation(s)", ("a/b.py:1: x imports outer layer y",))


def make(results: list[GateResult]) -> str:
    return render(
        results,
        language="python",
        fingerprint="f" * 64,
        config_sha256="c" * 64,
        policy=Policy(crap_ceiling=7, mutation_floor=91, max_exclusions=3),
        created="2026-10-16T12:00:00+00:00",
        command="gauntlet run .",
    )


def test_header_and_provenance() -> None:
    text = make([PASS])
    assert text.startswith("# Evidence report\n")
    assert "Generated 2026-10-16T12:00:00+00:00 by gauntlet " in text
    assert "`" + "f" * 64 + "`" in text
    assert "`" + "c" * 64 + "`" in text
    assert "crap ceiling 7, mutation floor 91, exclusion budget 3" in text


def test_gate_table_marks_pass_and_fail() -> None:
    text = make([PASS, FAIL])
    assert "| clean | PASS | clean: 5 function(s) checked, 0 over CRAP 8 |" in text
    assert "| arch | FAIL | arch: 3 module(s) checked, 1 violation(s) |" in text
    assert "**Overall: FAIL**" in text


def test_overall_pass() -> None:
    assert "**Overall: PASS**" in make([PASS])


def test_findings_are_listed_under_their_gate() -> None:
    text = make([PASS, FAIL])
    assert "### arch\n\n- `a/b.py:1: x imports outer layer y`\n" in text
    assert "### clean" not in text


def test_limits_and_reproduction_are_always_stated() -> None:
    text = make([PASS])
    assert "## What this does not prove" in text
    assert "forge" in text
    assert "```\ngauntlet run .\n```" in text


def test_pipes_in_summaries_cannot_break_the_table() -> None:
    odd = GateResult("clean", True, "a | b", ())
    assert "| clean | PASS | a \\| b |" in make([odd])
