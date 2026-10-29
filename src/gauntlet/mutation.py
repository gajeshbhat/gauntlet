"""Mutation reports of every language's tool, read into one score. The tools run in the sandbox (`gauntlet run`)."""

import json
import xml.etree.ElementTree as ET  # noqa: N817
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from gauntlet import harden
from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.linecov import parse_xml
from gauntlet.results import Mutation
from gauntlet.scope import Scope


@dataclass(frozen=True)
class Mutant:
    file: str  # project-relative
    line: int
    label: str  # what was changed and what happened, for the survivor list
    caught: bool  # the tests noticed; a mutant nothing exercised is NOT caught (fail closed)
    column: int | None = None  # gremlins reports one: its survivors read `file:line:column label`

    @property
    def survivor(self) -> str:
        if self.column is None:
            return f"{self.file}:{self.line}: {self.label}"
        return f"{self.file}:{self.line}:{self.column} {self.label}"


def tally(mutants: Iterable[Mutant], scope: Scope, tool: str) -> Mutation:
    """The score over the mutants in scope. Readers leave out mutants that do not count (compile errors, say)."""
    chosen = [m for m in mutants if scope.contains(m.file, m.line)]
    if not chosen:
        raise GauntletError(f"no mutants in scope; check the scope and that {tool} ran")
    caught = sum(m.caught for m in chosen)
    survivors = [m.survivor for m in chosen if not m.caught]
    return Mutation(100 * caught / len(chosen), survivors, caught, len(chosen))


GREMLINS_CAUGHT = {"KILLED", "TIMED OUT"}
GREMLINS_IGNORED = {"NOT VIABLE", "SKIPPED"}


def gremlins(text: str, scope: Scope, base: str = "") -> Mutation:
    """gremlins' mutation.json, its file names relative to `base` (the directory gremlins ran in). KILLED and
    TIMED OUT are caught; NOT VIABLE and SKIPPED are left out; any other status (LIVED, NOT COVERED) is not caught."""
    mutants = (
        Mutant(
            f"{base}/{f['file_name']}" if base else f["file_name"],
            m["line"],
            f"{m['type']} {m['status']}",
            m["status"] in GREMLINS_CAUGHT,
            m["column"],
        )
        for f in json.loads(text)["files"]
        for m in f["mutations"]
        if m["status"] not in GREMLINS_IGNORED
    )
    return tally(mutants, scope, "gremlins")


PIT_CAUGHT = {"KILLED", "TIMED_OUT", "MEMORY_ERROR"}
PIT_SURVIVED = {"SURVIVED", "NO_COVERAGE", "RUN_ERROR", "NOT_STARTED", "STARTED"}
PIT_IGNORED = {"NON_VIABLE"}
PIT_SOURCES = "src/main/java"  # Maven's default layout; the exclusions gate reports a pom that moves it


def pit(text: str, scope: Scope) -> Mutation:
    """PIT's mutations.xml. KILLED, TIMED_OUT (an endless loop the tests noticed) and MEMORY_ERROR (the mutant ran out
    of memory) are caught. SURVIVED and NO_COVERAGE (no test reaches the line) are not, and neither are RUN_ERROR (a
    crashed test JVM may be infrastructure, not the mutant), NOT_STARTED and STARTED (PIT did not finish). NON_VIABLE
    (the mutant does not compile) is left out. Any other status is an error."""
    rows = parse_xml("PIT", text).iter("mutation")
    return tally([_pit_mutant(el) for el in rows if el.get("status") not in PIT_IGNORED], scope, "PIT")


def _pit_mutant(el: ET.Element) -> Mutant:
    status = el.get("status", "")
    if status not in PIT_CAUGHT | PIT_SURVIVED:
        raise GauntletError(f"unknown PIT mutation status {status!r}")
    package = (el.findtext("mutatedClass") or "").rpartition(".")[0]
    file = "/".join(p for p in (PIT_SOURCES, *package.split("."), el.findtext("sourceFile") or "") if p)
    label = f"{el.findtext('mutator', '').rpartition('.')[2]} in {el.findtext('mutatedMethod')}: {status}"
    return Mutant(file, int(el.findtext("lineNumber") or 0), label, status in PIT_CAUGHT)


CARGO_CAUGHT = {"CaughtMutant", "Timeout"}


def _cargo_mutant(m: dict[str, Any], summary: str) -> Mutant:
    return Mutant(
        m["file"], m["span"]["start"]["line"], f"{m['genre']} {m['replacement']} {summary}", summary in CARGO_CAUGHT
    )


def cargo_mutants(text: str, scope: Scope) -> Mutation:
    """Read cargo-mutants' outcomes.json. CaughtMutant and Timeout are caught; MissedMutant is not. A mutant that
    does not compile (Unviable) is left out; any other status counts as not caught (fail closed). The baseline run
    is not a mutant and is left out."""
    report = json.loads(text)
    outcomes = [o for o in report["outcomes"] if isinstance(o["scenario"], dict)]
    if len(outcomes) < report["total_mutants"]:
        raise GauntletError(
            f"cargo-mutants finished {len(outcomes)} of {report['total_mutants']} mutants: partial report"
        )
    outcomes = [o for o in outcomes if o["summary"] != "Unviable"]
    mutants = [_cargo_mutant(o["scenario"]["Mutant"], o["summary"]) for o in outcomes]
    return tally(mutants, scope, "cargo-mutants")


def universalmutator(text: str, scope: Scope) -> Mutation:
    """gauntlet's own report of a universalmutator run (cppmutants.py). `killed` (the tests, or a test timeout, failed
    on the mutant) is caught. `survived` is not, and neither is any other status (fail closed). Mutants that do not
    build were already left out by `mutate --cmd`; a mutant whose rebuild fails later counts as survived."""
    mutants = (
        Mutant(m["file"], m["line"], f"{m['mutation']}: {m['status']}", m["status"] == "killed")
        for m in json.loads(text)["mutants"]
    )
    return tally(mutants, scope, "universalmutator")


@dataclass(frozen=True)
class Tool:
    artifact: str  # the file the sandbox run leaves behind
    how: str  # how to produce it yourself, for the error message
    read: Callable[[str, Scope, Config], Mutation]


SANDBOX_ROOT = "/project/"
STRYKER_CAUGHT = {"Killed", "Timeout", "RuntimeError"}  # a mutant that crashes the test run was noticed
STRYKER_IGNORED = {
    "CompileError",
    "Ignored",
}  # not a test result: left out (a disable comment is budgeted by the pragma)


def _stryker_path(name: str) -> str:
    """Stryker JS names files relative to the project, Stryker.NET by their absolute path in the container."""
    if not name.startswith("/"):
        return name
    if not name.startswith(SANDBOX_ROOT):
        raise GauntletError(f"Stryker reported {name}, outside {SANDBOX_ROOT}")
    return name.removeprefix(SANDBOX_ROOT)


def stryker_check(text: str, scope: Scope, tool: str = "Stryker") -> Mutation:
    """A JSON report in the mutation-testing-elements schema (Stryker, Mull) as one score.

    Killed, Timeout and RuntimeError count as caught. Survived and NoCoverage (no test ran the code) are NOT caught,
    and any status the tool adds later fails closed the same way. CompileError and Ignored are left out of the count
    (Ignored covers the tool's own filters; a disable comment is counted against the exclusion budget).
    """
    mutants = (
        Mutant(
            _stryker_path(name),
            m["location"]["start"]["line"],
            f"{m['mutatorName']} {m['status']}",
            m["status"] in STRYKER_CAUGHT,
        )
        for name, file in json.loads(text)["files"].items()
        for m in file["mutants"]
        if m["status"] not in STRYKER_IGNORED
    )
    return tally(mutants, scope, tool)


TOOLS: dict[str, Tool] = {
    "python": Tool(
        "mutmut-results.txt",
        "mutmut run && mutmut results --all true > mutmut-results.txt (or: gauntlet run)",
        lambda text, scope, cfg: harden.check(text),  # noqa: ARG005
    ),
    "go": Tool(
        "mutation.json",
        "gremlins unleash -o mutation.json .",
        lambda text, scope, cfg: gremlins(text, scope, cfg.mutation_dir),
    ),
    "javascript": Tool(
        "stryker.json",
        "npx @stryker-mutator/core run (testRunner command, jsonReporter fileName stryker.json) (or: gauntlet run)",
        lambda text, scope, cfg: stryker_check(text, scope),  # noqa: ARG005
    ),
    "java": Tool(
        "mutations.xml",
        "mvn test-compile org.pitest:pitest-maven:mutationCoverage -DoutputFormats=XML (then copy target/pit-reports)",
        lambda text, scope, cfg: pit(text, scope),  # noqa: ARG005
    ),
    "rust": Tool(
        "mutants-outcomes.json",
        "cargo mutants --no-config -o out && cp out/mutants.out/outcomes.json mutants-outcomes.json (or: gauntlet run)",
        lambda text, scope, cfg: cargo_mutants(text, scope),  # noqa: ARG005
    ),
    "cpp": Tool(
        "cpp-mutants.json",
        "see src/gauntlet/cppmutants.py: universalmutator over the CMake project (or: gauntlet run)",
        lambda text, scope, cfg: universalmutator(text, scope),  # noqa: ARG005
    ),
    "csharp": Tool(
        "stryker-report.json",
        "dotnet stryker --reporter json, then copy StrykerOutput/*/reports/mutation-report.json to"
        " stryker-report.json (or: gauntlet run)",
        lambda text, scope, cfg: stryker_check(text, scope),  # noqa: ARG005
    ),
    "cpp-clang": Tool(
        "mull-report.json",
        "mull-runner-21 <test binary> --reporters Elements, merge the reports as mull-report.json (or: gauntlet run)",
        lambda text, scope, cfg: stryker_check(text, scope, "Mull"),  # noqa: ARG005
    ),
}
