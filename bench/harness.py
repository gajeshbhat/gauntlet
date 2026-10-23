"""Planted-bug benchmark: does gauntlet fail an agent-written change whose own tests miss a bug?

Each task is a small repository (tasks/<task>/repo), a hidden test suite the patch author never sees
(tasks/<task>/hidden) and cases (tasks/<task>/cases/<case>: meta.json plus the files the patch writes). A case is run
through three checkers: the visible tests alone, the visible tests plus 80% coverage, and `gauntlet run`. The hidden
tests decide whether the patch is really buggy. Everything that executes project code runs in a Docker sandbox.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gauntlet import languages
from gauntlet.docker import DockerSandbox

HERE = Path(__file__).parent
KINDS = ("reference", "weak-tests", "natural", "planted", "gaming")
CHECKERS = ("baseline", "coverage", "gauntlet")
COVERAGE_FLOOR = 80.0
GIT = ("-c", "user.name=bench", "-c", "user.email=bench@localhost", "-c", "commit.gpgsign=false")

Row = dict[str, Any]


@dataclass(frozen=True)
class Case:
    task: str
    name: str
    # reference: correct code, careful tests; weak-tests: correct code, agent-typical tests; natural: an agent's
    # patch; planted: a bug the careful tests miss; gaming: a bug plus a cheat that hides it
    kind: str
    bug: str  # the bug class planted, or the cheat used
    files: Path  # the files the patch writes, laid over the task's repository
    base: tuple[str, ...] = ()  # cases of the task whose files are laid down first, in order (reuse tests and bugs)


def load_cases(tasks: Path) -> list[Case]:
    found: list[Case] = []
    for meta_path in sorted(tasks.glob("*/cases/*/meta.json")):
        meta = json.loads(meta_path.read_text())
        if meta["kind"] not in KINDS:
            raise ValueError(f"{meta_path}: unknown kind {meta['kind']!r}")
        case_dir = meta_path.parent
        task = case_dir.parent.parent.name
        found.append(
            Case(
                task, case_dir.name, meta["kind"], meta.get("bug", ""), case_dir / "files", tuple(meta.get("base", ()))
            )
        )
    return found


def assemble(tasks: Path, case: Case, dest: Path) -> None:
    """The shared template, the task's repository, the base case's files, then the case's own, committed (gauntlet
    binds results to a commit). Every task uses the package name `task`, so one template fits all."""
    shutil.copytree(tasks.parent / "template", dest)
    base = [tasks / case.task / "cases" / name / "files" for name in case.base]
    for layer in (tasks / case.task / "repo", *base, case.files):
        shutil.copytree(layer, dest, dirs_exist_ok=True)
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", case.name)):
        subprocess.run(["git", *GIT, "-C", str(dest), *args], check=True, capture_output=True)


def outcome(code: int, stderr: str, results: list[Row]) -> Row:
    """What `gauntlet run` said: exit 2 with a failed tests step means the visible tests failed."""
    tests_failed = code == 2 and "step 'tests' failed" in stderr
    error = stderr.strip()[-300:] if code == 2 and not tests_failed else ""
    gates = [r["gate"] for r in results if not r["ok"]]
    mutation = next((r["stats"]["score"] for r in results if r["gate"] == "harden" and "stats" in r), None)
    row = {"gauntlet_fail": code != 0, "tests_failed": tests_failed, "gates": gates, "error": error}
    return row | {"mutation": mutation}


def coverage_pct(path: Path) -> float | None:
    return float(json.loads(path.read_text())["totals"]["percent_covered"]) if path.is_file() else None


def checkers(row: Row) -> dict[str, bool]:
    """Whether each checker fails the patch. No coverage report (the tests failed first) counts as a failure."""
    low = row["coverage"] is None or row["coverage"] < COVERAGE_FLOOR
    return {
        "baseline": row["tests_failed"],
        "coverage": row["tests_failed"] or low,
        "gauntlet": row["gauntlet_fail"],
    }


def validity(rows: list[Row]) -> list[str]:
    """Cases that do not test what they claim: they are reported and left out of the score."""
    problems: list[str] = []
    for r in rows:
        name = f"{r['task']}/{r['case']}"
        if r["kind"] == "planted" and r["hidden_pass"]:
            problems.append(f"{name}: planted bug passes the hidden tests")
        elif r["kind"] == "planted" and r["tests_failed"]:
            problems.append(f"{name}: planted bug fails the visible tests")
        elif r["kind"] == "reference" and not r["hidden_pass"]:
            problems.append(f"{name}: reference fails the hidden tests")
        elif r["kind"] == "weak-tests" and not r["hidden_pass"]:
            problems.append(f"{name}: weak-tests code fails the hidden tests")
    return problems


def should_fail(row: Row) -> bool:
    """A buggy patch should fail, and so should correct code whose tests are too thin to show it."""
    return not row["hidden_pass"] or row["kind"] == "weak-tests"


def _valid(rows: list[Row]) -> list[Row]:
    bad = {p.split(":")[0] for p in validity(rows)}
    return [r for r in rows if f"{r['task']}/{r['case']}" not in bad]


def score(rows: list[Row]) -> dict[str, dict[str, dict[str, int]]]:
    """Per kind (and over all), per checker: patches that should fail and did, and patches that should pass but
    failed (false alarms)."""
    scores: dict[str, dict[str, dict[str, int]]] = {}
    for r in rows:
        fail = should_fail(r)
        verdicts = checkers(r)
        for kind in (r["kind"], "all"):
            for name in CHECKERS:
                cell = scores.setdefault(kind, {}).setdefault(
                    name, {"caught": 0, "should_fail": 0, "alarms": 0, "should_pass": 0}
                )
                cell["should_fail" if fail else "should_pass"] += 1
                cell["caught" if fail else "alarms"] += verdicts[name]
    return scores


def _ratio(hit: int, total: int) -> str:
    return f"{hit}/{total}" if total else "-"


def report(rows: list[Row]) -> str:
    valid = _valid(rows)
    lines = ["| Cases | Checker | Caught | False alarms |", "|---|---|---|---|"]
    for kind, by_checker in sorted(score(valid).items(), key=lambda item: (item[0] == "all", item[0])):
        for name in CHECKERS:
            c = by_checker[name]
            caught, alarms = _ratio(c["caught"], c["should_fail"]), _ratio(c["alarms"], c["should_pass"])
            lines.append(f"| {kind} | {name} | {caught} | {alarms} |")
    gates = Counter(g for r in valid if should_fail(r) for g in r["gates"])
    lines += ["", "| Gate | Patches it rightly failed |", "|---|---|"]
    lines += [f"| {gate} | {n} |" for gate, n in gates.most_common()]
    lines += ["", "| Case | Kind | Should | gauntlet | Mutation % | Coverage % |", "|---|---|---|---|---|---|"]
    for r in valid:
        expected, got = ("fail" if v else "pass" for v in (should_fail(r), r["gauntlet_fail"]))
        mutation, coverage = (f"{v:.1f}" if v is not None else "-" for v in (r.get("mutation"), r["coverage"]))
        lines.append(f"| {r['task']}/{r['case']} | {r['kind']} | {expected} | {got} | {mutation} | {coverage} |")
    problems = validity(rows)
    if problems:
        lines += ["", "Invalid cases (left out): " + "; ".join(problems)]
    return "\n".join(lines) + "\n"


def hidden_pass(tasks: Path, case: Case, dest: Path) -> bool:  # pragma: no cover - runs a container
    """Run only the task's hidden tests against the patched repository, in the sandbox: the patch's own tests do not
    decide whether it is correct."""
    hidden = dest / "hidden_tests"
    shutil.copytree(tasks / case.task / "hidden", hidden)
    names = sorted(f"hidden_tests/{p.name}" for p in hidden.glob("test_*.py"))
    box = DockerSandbox(dest, languages.TABLE["python"].image, memory="2g")
    box.ensure()
    try:
        done = box.exec(
            [
                "uv",
                "run",
                "--project",
                "/project",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--import-mode=importlib",
                *names,
            ],
            timeout=300,  # a planted bug can loop forever
        )
    finally:
        box.remove()
    return done.code == 0


def run_case(tasks: Path, case: Case, policy: Path, work: Path) -> Row:  # pragma: no cover - runs containers
    dest, results = work / f"{case.task}-{case.name}", work / f"{case.task}-{case.name}.json"
    assemble(tasks, case, dest)
    started = time.monotonic()
    cmd = ["gauntlet", "run", str(dest), "--policy", str(policy), "--json", str(results)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    seconds = round(time.monotonic() - started)
    gate_results: list[Row] = json.loads(results.read_text()) if results.is_file() else []
    row: Row = {"task": case.task, "case": case.name, "kind": case.kind, "bug": case.bug}
    row |= outcome(done.returncode, done.stderr, gate_results)
    row |= {"coverage": coverage_pct(dest / ".gauntlet" / "coverage.json"), "seconds": seconds}
    row["hidden_pass"] = hidden_pass(tasks, case, dest)
    return row


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - the command line
    parser = argparse.ArgumentParser(prog="bench")
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--task", action="append", help="only these tasks")
    parser.add_argument("--results", type=Path, default=HERE / "results.jsonl")
    args = parser.parse_args(argv)
    if args.command == "run":
        cases = [c for c in load_cases(HERE / "tasks") if not args.task or c.task in args.task]
        with tempfile.TemporaryDirectory(prefix="gauntlet-bench-") as tmp, args.results.open("w") as out:
            for i, case in enumerate(cases, 1):
                row = run_case(HERE / "tasks", case, HERE / "policy.toml", Path(tmp))
                out.write(json.dumps(row) + "\n")
                out.flush()
                print(f"[{i}/{len(cases)}] {case.task}/{case.name}: {checkers(row)} hidden_pass={row['hidden_pass']}")
        return 0
    rows = [json.loads(line) for line in args.results.read_text().splitlines() if line.strip()]
    text = report(rows)
    (HERE / "RESULTS.md").write_text("# Benchmark results\n\n" + text)
    print(text, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
