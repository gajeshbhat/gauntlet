import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet.harden import check, score

RESULTS = """
    pkg.x_a__mutmut_1: killed
    pkg.x_a__mutmut_2: survived
    pkg.x_b__mutmut_1: timeout
    pkg.x_b__mutmut_2: skipped
    pkg.x_c__mutmut_1: no tests
"""


def test_score_counts_killed_and_timeout_and_ignores_skipped() -> None:
    assert score(RESULTS) == (2, 4, ["pkg.x_a__mutmut_2: survived", "pkg.x_c__mutmut_1: no tests"])


def test_score_of_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match="^no mutants found"):
        score("")


Run = Callable[..., subprocess.CompletedProcess[str]]


def fake_run(results: str) -> tuple[Run, list[list[str]], list[dict[str, object]]]:
    calls: list[list[str]] = []
    options: list[dict[str, object]] = []

    def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        options.append(kwargs)
        out = results if "results" in cmd else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")

    return run, calls, options


def test_check_runs_mutmut_then_reads_results(tmp_path: Path) -> None:
    run, calls, options = fake_run(RESULTS)
    pct, survivors = check(tmp_path, run=run)
    assert pct == 50.0
    assert len(survivors) == 2
    base = ["uv", "run", "--project", str(tmp_path), "mutmut"]
    assert calls == [[*base, "run"], [*base, "results", "--all", "true"]]
    expected = {"cwd": tmp_path, "capture_output": True, "text": True}
    assert options == [expected, expected]
