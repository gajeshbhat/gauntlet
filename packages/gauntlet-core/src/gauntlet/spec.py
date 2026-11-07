"""Check a Gherkin spec: well-formed, every scenario has When/Then and traces to a real test via @test(path::name)."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text

MAX_SPEC_BYTES = 100_000
STEP = re.compile(r"^(Given|When|Then|And|But|\*)\s+(.*)$")
TEST_TAG = re.compile(r"^test\((.+)\)$")
PARAM = re.compile(r"<([^<>]+)>")


@dataclass(frozen=True)
class Scenario:
    name: str
    tags: tuple[str, ...]
    steps: tuple[tuple[str, str], ...]
    outline: bool
    examples: tuple[tuple[str, ...], ...]


@dataclass
class _Draft:
    name: str
    tags: tuple[str, ...]
    outline: bool
    steps: list[tuple[str, str]] = field(default_factory=lambda: list[tuple[str, str]]())
    examples: list[tuple[str, ...]] = field(default_factory=lambda: list[tuple[str, ...]]())

    def freeze(self) -> Scenario:
        return Scenario(self.name, self.tags, tuple(self.steps), self.outline, tuple(self.examples))


@dataclass(frozen=True)
class Feature:
    name: str
    background: tuple[str, ...]
    scenarios: tuple[Scenario, ...]
    problems: tuple[str, ...]


class _Parser:
    def __init__(self) -> None:
        self.name = ""
        self.features = 0
        self.background: list[str] = []
        self.scenarios: list[_Draft] = []
        self.problems: list[str] = []
        self.tags: tuple[str, ...] = ()
        self.mode = ""
        self.last_keyword = "Given"

    def line(self, n: int, text: str) -> None:
        if text.startswith("@"):
            self.tags = (*self.tags, *[t[1:] for t in text.split() if t.startswith("@")])
        elif text.startswith("|"):
            self.row(n, text)
        elif not (":" in text and self.heading(n, text)):
            self.step_or_text(n, text)

    def step_or_text(self, n: int, text: str) -> None:
        step = STEP.match(text)
        if step is not None:
            self.step(n, step[1], step[2])
        elif self.mode != "feature":  # free text under "Feature:" is the description Gherkin allows
            self.problems.append(f"line {n}: not understood: {text!r}")

    def heading(self, n: int, text: str) -> bool:
        head, _, rest = text.partition(":")
        rest = rest.strip()
        if head == "Feature":
            self.mode = "feature"
            self.features += 1
            self.name = self.name or rest
            if not rest:
                self.problems.append(f"line {n}: Feature has no name")
        elif head == "Background":
            self.mode = "background"
        elif head in ("Scenario", "Example", "Scenario Outline", "Scenario Template"):
            self.scenario(n, rest, head.startswith("Scenario ") and head != "Scenario")
        elif head in ("Examples", "Scenarios"):
            self.mode = "examples"
        else:
            return False
        return True

    def scenario(self, n: int, name: str, outline: bool) -> None:
        if not name:
            self.problems.append(f"line {n}: Scenario has no name")
        self.scenarios.append(_Draft(name, self.tags, outline))
        self.tags, self.mode, self.last_keyword = (), "scenario", "Given"

    def step(self, n: int, keyword: str, text: str) -> None:
        keyword = self.last_keyword if keyword in ("And", "But", "*") else keyword
        self.last_keyword = keyword
        if self.mode == "background":
            self.background.append(f"{keyword} {text}")
        elif self.scenarios and self.mode in ("scenario", "examples"):
            self.scenarios[-1].steps.append((keyword, text))
        else:
            self.problems.append(f"line {n}: step outside a scenario")

    def row(self, n: int, text: str) -> None:
        if self.scenarios and self.mode == "examples":
            self.scenarios[-1].examples.append(tuple(c.strip() for c in text.strip("|").split("|")))
        else:
            self.problems.append(f"line {n}: table row outside Examples")


def parse(text: str) -> Feature:
    p = _Parser()
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line and not line.startswith("#"):
            p.line(n, line)
    problems = list(p.problems)
    if p.features == 0:
        problems.append("no Feature")
    if p.features > 1:
        problems.append("more than one Feature")
    return Feature(p.name, tuple(p.background), tuple(s.freeze() for s in p.scenarios), tuple(problems))


def _table_problems(s: Scenario) -> list[str]:
    header, rows = s.examples[0], s.examples[1:]
    found = [f"'{s.name}' has an Examples table with no rows"] if not rows else []
    found += [f"'{s.name}' uses <{p}> but Examples has no such column" for p in _params(s) if p not in header]
    found += [
        f"'{s.name}' Examples row {i} has {len(r)} cells, header has {len(header)}"
        for i, r in enumerate(rows, 2)
        if len(r) != len(header)
    ]
    return found


def _outline_problems(s: Scenario) -> list[str]:
    if not s.outline:
        return [f"'{s.name}' has Examples but is not an outline"] if s.examples else []
    return _table_problems(s) if s.examples else [f"'{s.name}' is an outline without Examples"]


def _params(s: Scenario) -> list[str]:
    return sorted({p for _, text in s.steps for p in PARAM.findall(text)})


def _trace(ref: str, root: Path) -> list[str]:
    path, _, name = ref.partition("::")
    try:
        target = inside(root, path)
    except ValueError as e:
        return [str(e)]
    if not target.is_file():
        return [f"{path} does not exist"]
    if name and not re.search(rf"\b{re.escape(name.split('::')[-1])}\b", read_text(target, MAX_SOURCE_BYTES)):
        return [f"{name} is not in {path}"]
    return []


def _step_problems(s: Scenario) -> list[str]:
    kinds = {k for k, _ in s.steps}
    return [f"'{s.name}' has no {k}" for k in ("When", "Then") if k not in kinds]


def _trace_problems(s: Scenario, root: Path) -> list[str]:
    refs = [m[1] for m in (TEST_TAG.match(t) for t in s.tags) if m]
    if not refs:
        return [f"'{s.name}' has no @test(...) tag"]
    return [p for r in refs for p in _trace(r, root)]


def check(path: Path, root: Path) -> list[str]:
    feature = parse(read_text(path, MAX_SPEC_BYTES))
    problems = list(feature.problems)
    if not feature.scenarios:
        problems.append("the Feature has no scenarios")
    for s in feature.scenarios:
        problems += _step_problems(s) + _trace_problems(s, root) + _outline_problems(s)
    return problems
