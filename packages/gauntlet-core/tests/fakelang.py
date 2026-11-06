"""A tiny stand-in language plugin, so core tests never depend on the real Python plugin.

It reads the same simple files the core tests write: `.py`-named sources (lizard measures them), a coverage.json,
"name: status" mutation lines, "import x" / "from x import y" lines, "#" comments and an `excludes.txt` config.
"""

import json
import re
from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.plugin import Language, Lines, MutationTool, Step
from gauntlet.results import Mutation


def steps(src: str, project: str, out: str, tool: str) -> list[Step]:
    return [
        Step("tests", ("fake-test", src, out), timeout=3600),
        Step("mutation", ("fake-mutate", tool), timeout=7200, must_pass=False),
        Step("mutation-results", ("fake-results",), "mutmut-results.txt"),
    ]


def coverage(text: str) -> Lines:
    files: dict[str, dict[str, list[int]]] = json.loads(text)["files"]
    return {
        name: {**{n: 0 for n in data["missing_lines"]}, **{n: 1 for n in data["executed_lines"]}}
        for name, data in files.items()
    }


def mutants(text: str) -> Mutation:
    statuses = [line.partition(": ") for line in text.splitlines() if ": " in line]
    caught = sum(status == "killed" for _, _, status in statuses)
    bad = [f"{name}: {status}" for name, _, status in statuses if status != "killed"]
    if not statuses:
        raise GauntletError("no mutants found")
    return Mutation(100 * caught / len(statuses), bad, caught, len(statuses))


def imports(source: str, package: list[str]) -> list[tuple[int, str]]:
    if "BROKEN" in source:
        raise GauntletError("BrokenSource")
    found: list[tuple[int, str]] = []
    for n, line in enumerate(source.splitlines(), 1):
        if m := re.match(r"(?:import|from) ([\w.]+)", line):
            found.append((n, m[1]))
            if line.startswith("from") and (rest := re.search(r"import (\w+)", line)):
                found.append((n, f"{m[1]}.{rest[1]}"))
    return found


def comments(text: str) -> list[tuple[int, str]]:
    if "BROKEN" in text:
        raise GauntletError("BrokenSource")
    return [(n, line[line.index("#") :]) for n, line in enumerate(text.splitlines(), 1) if "#" in line]


def config_excludes(root: Path) -> list[str]:
    path = root / "excludes.txt"
    return [f"excludes.txt: {line}" for line in path.read_text().splitlines()] if path.is_file() else []


FAKE = Language(
    suffixes=(".py",),
    markers=("fake.marker",),
    tests=r"^(tests?/|conftest\.py$)",
    pragma=r"#\s*(?:pragma:\s*no\s+(?:mutate|cover)|nosec)\b",
    coverage_file="coverage.json",
    image="example.com/fake:1",
    artifacts=("coverage.json", "mutmut-results.txt"),
    steps=steps,
    read_coverage=coverage,
    mutation={
        "mutmut": MutationTool("mutmut-results.txt", "run the fake mutator (or: gauntlet run)", mutants),
        "other": MutationTool("mutmut-results.txt", "run the other fake mutator (or: gauntlet run)", mutants),
    },
    imports=imports,
    comments=comments,
    config_excludes=config_excludes,
    template=lambda root: f'language = "fake"\nsrc = "{"src" if (root / "src").is_dir() else "."}"\n# [layers]\n',
)
