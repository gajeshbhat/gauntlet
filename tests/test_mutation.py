import json
from pathlib import Path

import pytest

from gauntlet import mutation
from gauntlet.config import Config
from gauntlet.mutation import Mutant, tally
from gauntlet.scope import parse

M = [Mutant("a.js", 3, "ArithmeticOperator Survived", False), Mutant("a.js", 9, "BooleanLiteral Killed", True)]


def test_score_is_caught_over_counted_and_survivors_are_listed() -> None:
    pct, survivors, caught, total = tally(M, parse([]), "Stryker")
    assert (pct, survivors, caught, total) == (50.0, ["a.js:3: ArithmeticOperator Survived"], 1, 2)


def test_scope_limits_the_mutants_counted() -> None:
    assert tally(M, parse(["a.js:5-12"]), "Stryker") == (100.0, [], 1, 1)


def test_no_mutants_in_scope_is_an_error_not_a_pass() -> None:
    with pytest.raises(ValueError, match="no mutants in scope; check the scope and that Stryker ran"):
        tally(M, parse(["other.js"]), "Stryker")
    with pytest.raises(ValueError, match="no mutants in scope"):
        tally([], parse([]), "Stryker")


def test_python_and_go_readers_are_registered() -> None:
    py, go = mutation.TOOLS["python"], mutation.TOOLS["go"]
    assert py.read("p.x: killed\np.y: survived\n", parse([]), Config(language="python")).pct == 50.0
    text = (
        '{"files": [{"file_name": "a.go", "mutations": [{"line": 1, "column": 2, "type": "T", "status": "KILLED"}]}]}'
    )
    assert go.read(text, parse([]), Config(language="go")).pct == 100.0
    assert (py.artifact, go.artifact) == ("mutmut-results.txt", "mutation.json")


# a real report from `stryker run` in the sandbox (7 of 28 mutants, each with the fields the reader uses)
STRYKER_REPORT = """{"schemaVersion":"1.0","files":{"index.js":{"language":"javascript","mutants":[{"id":"0","mutatorName":"BlockStatement","replacement":"{}","status":"Killed","location":{"end":{"column":2,"line":4},"start":{"column":15,"line":1}}},{"id":"1","mutatorName":"ConditionalExpression","replacement":"true","status":"Killed","location":{"end":{"column":12,"line":2},"start":{"column":7,"line":2}}},{"id":"3","mutatorName":"EqualityOperator","replacement":"x >= 1","status":"Survived","location":{"end":{"column":12,"line":2},"start":{"column":7,"line":2}}},{"id":"4","mutatorName":"EqualityOperator","replacement":"x <= 1","status":"Killed","location":{"end":{"column":12,"line":2},"start":{"column":7,"line":2}}},{"id":"7","mutatorName":"ConditionalExpression","replacement":"true","status":"Survived","location":{"end":{"column":14,"line":6},"start":{"column":7,"line":6}}},{"id":"6","mutatorName":"BlockStatement","replacement":"{}","status":"Survived","location":{"end":{"column":2,"line":12},"start":{"column":19,"line":5}}},{"id":"27","mutatorName":"ObjectLiteral","replacement":"{}","status":"Killed","location":{"end":{"column":30,"line":13},"start":{"column":18,"line":13}}}]}}}"""


def stryker_report(*statuses: str) -> str:
    mutants = [{"mutatorName": "M", "status": s, "location": {"start": {"line": n}}} for n, s in enumerate(statuses, 1)]
    return json.dumps({"files": {"a.js": {"mutants": mutants}}})


def test_stryker_real_report_is_scored_with_survivors_by_line() -> None:
    m = mutation.TOOLS["javascript"].read(STRYKER_REPORT, parse([]), Config(language="javascript"))
    assert (m.caught, m.total) == (4, 7)
    assert m.survivors == [
        "index.js:2: EqualityOperator Survived",
        "index.js:6: ConditionalExpression Survived",
        "index.js:5: BlockStatement Survived",
    ]
    assert mutation.TOOLS["javascript"].artifact == "stryker.json"


@pytest.mark.parametrize(
    ("status", "caught"),
    [("Killed", True), ("Timeout", True), ("RuntimeError", True), ("Survived", False), ("NoCoverage", False)]
    + [("Pending", False)],  # unknown to us: fails closed
)
def test_stryker_status_mapping(status: str, caught: bool) -> None:
    m = mutation.stryker_check(stryker_report(status), parse([]))
    assert (m.caught, m.total) == (int(caught), 1)


def test_stryker_compile_errors_and_ignored_mutants_are_left_out() -> None:
    m = mutation.stryker_check(stryker_report("Killed", "CompileError", "Ignored"), parse([]))
    assert (m.caught, m.total) == (1, 1)


PIT_REPORT = (Path(__file__).parent / "fixtures" / "pit-mutations.xml").read_text()  # captured from a container run


JAVA = Config(language="java")


def pit_report(*statuses: str) -> str:
    rows = "".join(
        f"<mutation detected='false' status='{s}'><sourceFile>A.java</sourceFile><mutatedClass>com.x.A</mutatedClass>"
        f"<mutatedMethod>f</mutatedMethod><lineNumber>{n}</lineNumber><mutator>a.b.MathMutator</mutator></mutation>"
        for n, s in enumerate(statuses, 1)
    )
    return f"<mutations>{rows}</mutations>"


def test_java_reads_a_real_pit_report() -> None:
    pct, survivors, caught, total = mutation.TOOLS["java"].read(PIT_REPORT, parse([]), JAVA)
    assert (caught, total) == (2, 13)
    assert pct == pytest.approx(100 * 2 / 13)
    assert survivors[0] == "src/main/java/com/x/A.java:4: ConditionalsBoundaryMutator in f: SURVIVED"
    assert len(survivors) == 11
    assert mutation.TOOLS["java"].artifact == "mutations.xml"


@pytest.mark.parametrize(
    ("status", "caught"),
    [
        ("KILLED", True),
        ("TIMED_OUT", True),
        ("MEMORY_ERROR", True),
        ("SURVIVED", False),
        ("NO_COVERAGE", False),
        ("RUN_ERROR", False),
        ("NOT_STARTED", False),
        ("STARTED", False),
    ],
)
def test_java_status_mapping(status: str, caught: bool) -> None:
    result = mutation.pit(pit_report(status, "KILLED"), parse([]), JAVA)
    assert result.total == 2
    assert result.caught == (2 if caught else 1)


def test_java_leaves_non_viable_mutants_out_and_rejects_unknown_statuses() -> None:
    assert mutation.pit(pit_report("NON_VIABLE", "KILLED"), parse([]), JAVA).total == 1
    with pytest.raises(ValueError, match="unknown PIT mutation status 'WEIRD'"):
        mutation.pit(pit_report("WEIRD"), parse([]), JAVA)


def test_java_maps_the_default_package_and_scope() -> None:
    text = pit_report("SURVIVED").replace("com.x.A", "A")
    assert mutation.pit(text, parse(["src/main/java/A.java:1-1"]), JAVA).survivors == [
        "src/main/java/A.java:1: MathMutator in f: SURVIVED"
    ]


def test_java_refuses_entities_in_the_report() -> None:
    with pytest.raises(ValueError, match="DOCTYPE"):
        mutation.pit('<!DOCTYPE x [<!ENTITY a "b">]><mutations/>', parse([]), JAVA)


# From a real cargo-mutants 27.1.0 run in the rust image (trimmed to the fields the reader uses).
CARGO_REPORT = (
    '{"total_mutants": 3, "outcomes": [{"scenario": "Baseline", "summary": "Success"},'
    ' {"scenario": {"Mutant": {"name": "src/lib.rs:2:5: replace f -> i32 with 0", "file": "src/lib.rs",'
    ' "replacement": "0", "genre": "FnValue", "span": {"start": {"line": 2, "column": 5}}}},'
    ' "summary": "CaughtMutant"},'
    ' {"scenario": {"Mutant": {"name": "src/lib.rs:2:10: replace > with >= in f", "file": "src/lib.rs",'
    ' "replacement": ">=", "genre": "BinaryOperator", "span": {"start": {"line": 2, "column": 10}}}},'
    ' "summary": "MissedMutant"},'
    ' {"scenario": {"Mutant": {"name": "src/lib.rs:6:10: replace == with != in risky", "file": "src/lib.rs",'
    ' "replacement": "!=", "genre": "BinaryOperator", "span": {"start": {"line": 6, "column": 10}}}},'
    ' "summary": "MissedMutant"}]}'
)


def cargo(summary: str) -> str:
    return CARGO_REPORT.replace('"summary": "MissedMutant"}]}', f'"summary": "{summary}"}}]}}')


def test_cargo_mutants_report_scores_caught_over_tested_and_lists_survivors_with_file_and_line() -> None:
    m = mutation.cargo_mutants(CARGO_REPORT, parse([]))
    assert (m.caught, m.total, round(m.pct, 1)) == (1, 3, 33.3)
    assert m.survivors == [
        "src/lib.rs:2: BinaryOperator >= MissedMutant",
        "src/lib.rs:6: BinaryOperator != MissedMutant",
    ]


@pytest.mark.parametrize(
    ("summary", "caught", "total"),
    [("CaughtMutant", 2, 3), ("Timeout", 2, 3), ("MissedMutant", 1, 3), ("Unviable", 1, 2), ("Failure", 1, 3)],
)
def test_cargo_mutants_statuses(summary: str, caught: int, total: int) -> None:
    m = mutation.cargo_mutants(cargo(summary), parse([]))
    assert (m.caught, m.total) == (caught, total)


def test_cargo_mutants_is_registered_and_the_baseline_alone_is_an_error() -> None:
    tool = mutation.TOOLS["rust"]
    assert tool.artifact == "mutants-outcomes.json"
    assert tool.read(CARGO_REPORT, parse([]), Config(language="rust")).total == 3
    with pytest.raises(ValueError, match="no mutants in scope; check the scope and that cargo-mutants ran"):
        tool.read(
            '{"total_mutants": 0, "outcomes": [{"scenario": "Baseline", "summary": "Success"}]}',
            parse([]),
            Config(language="rust"),
        )


# A real Stryker.NET 4.8.1 report (Demo project: F is tested, Risky is not), trimmed to the fields the reader uses.
STRYKER_NET_REPORT = (
    '{"schemaVersion":"2","files":{"/project/src/Demo/Calc.cs":{"language":"cs","mutants":[{"id":"0","mut'
    'atorName":"Block removal mutation","replacement":"{}","location":{"start":{"line":5,"column":5}},"st'
    'atus":"Ignored","statusReason":"Removed by block already covered filter"},{"id":"1","mutatorName":"E'
    'quality mutation","replacement":"x < 1","location":{"start":{"line":6,"column":13}},"status":"Killed'
    '"},{"id":"2","mutatorName":"Equality mutation","replacement":"x >= 1","location":{"start":{"line":6,'
    '"column":13}},"status":"Survived"},{"id":"3","mutatorName":"Negate expression","replacement":"!(x > '
    '1)","location":{"start":{"line":6,"column":13}},"status":"Killed"},{"id":"4","mutatorName":"Block re'
    'moval mutation","replacement":"{}","location":{"start":{"line":6,"column":20}},"status":"Killed"},{"'
    'id":"5","mutatorName":"Block removal mutation","replacement":"{}","location":{"start":{"line":10,"co'
    'lumn":5}},"status":"Ignored","statusReason":"Removed by block already covered filter"},{"id":"6","mu'
    'tatorName":"Equality mutation","replacement":"a != 1","location":{"start":{"line":11,"column":13}},"'
    'status":"NoCoverage","statusReason":"Not covered by any test."},{"id":"7","mutatorName":"Block remov'
    'al mutation","replacement":"{}","location":{"start":{"line":11,"column":21}},"status":"NoCoverage","'
    'statusReason":"Not covered by any test."},{"id":"8","mutatorName":"Equality mutation","replacement":'
    '"a != 2","location":{"start":{"line":12,"column":13}},"status":"NoCoverage","statusReason":"Not cove'
    'red by any test."},{"id":"9","mutatorName":"Block removal mutation","replacement":"{}","location":{"'
    'start":{"line":12,"column":21}},"status":"NoCoverage","statusReason":"Not covered by any test."},{"i'
    'd":"10","mutatorName":"Equality mutation","replacement":"a != 3","location":{"start":{"line":13,"col'
    'umn":13}},"status":"NoCoverage","statusReason":"Not covered by any test."},{"id":"11","mutatorName":'
    '"Block removal mutation","replacement":"{}","location":{"start":{"line":13,"column":21}},"status":"N'
    'oCoverage","statusReason":"Not covered by any test."},{"id":"12","mutatorName":"Equality mutation","'
    'replacement":"a != 4","location":{"start":{"line":14,"column":13}},"status":"NoCoverage","statusReas'
    'on":"Not covered by any test."},{"id":"13","mutatorName":"Block removal mutation","replacement":"{}"'
    ',"location":{"start":{"line":14,"column":21}},"status":"NoCoverage","statusReason":"Not covered by a'
    'ny test."},{"id":"14","mutatorName":"Equality mutation","replacement":"a != 5","location":{"start":{'
    '"line":15,"column":13}},"status":"NoCoverage","statusReason":"Not covered by any test."},{"id":"15",'
    '"mutatorName":"Block removal mutation","replacement":"{}","location":{"start":{"line":15,"column":21'
    '}},"status":"NoCoverage","statusReason":"Not covered by any test."}]}}}'
)


def _net(*statuses: str) -> str:
    mutants = [{"mutatorName": "M", "status": s, "location": {"start": {"line": 3}}} for s in statuses]
    return json.dumps({"files": {"/project/src/A.cs": {"mutants": mutants}}})


def test_stryker_net_reader_scores_a_real_report() -> None:
    m = mutation.TOOLS["csharp"].read(STRYKER_NET_REPORT, parse([]), Config(language="csharp"))
    assert (m.caught, m.total, round(m.pct, 1)) == (3, 14, 21.4)  # Stryker's own 21.43%
    assert "src/Demo/Calc.cs:6: Equality mutation Survived" in m.survivors
    assert "src/Demo/Calc.cs:11: Equality mutation NoCoverage" in m.survivors


@pytest.mark.parametrize(
    ("status", "caught", "total"),
    [
        ("Killed", 1, 1),
        ("Timeout", 1, 1),
        ("RuntimeError", 1, 1),
        ("Survived", 0, 1),
        ("NoCoverage", 0, 1),
        ("Pending", 0, 1),
        ("SomethingNew", 0, 1),
        ("CompileError", 0, 0),
        ("Ignored", 0, 0),
    ],
)
def test_stryker_net_status_mapping_fails_closed(status: str, caught: int, total: int) -> None:
    text = _net(status, "Killed")
    m = mutation.TOOLS["csharp"].read(text, parse([]), Config(language="csharp"))
    assert (m.caught - 1, m.total - 1) == (caught, total)


def test_stryker_net_refuses_files_outside_the_project() -> None:
    text = _net("Killed").replace("/project/src", "/etc")
    with pytest.raises(ValueError, match="outside /project/"):
        mutation.TOOLS["csharp"].read(text, parse([]), Config(language="csharp"))


def test_cargo_mutants_report_that_finished_fewer_mutants_than_planned_is_refused() -> None:
    partial = CARGO_REPORT.replace('"total_mutants": 3', '"total_mutants": 40')
    with pytest.raises(ValueError, match="finished 3 of 40 mutants: partial report"):
        mutation.cargo_mutants(partial, parse([]))
