"""The contract a language plugin fills in. Core never names a language; it calls these fields.

A plugin is one `Language` value, registered under the `gauntlet.languages` entry-point group (see languages.py).
Every callable that reads untrusted input raises `GauntletError` for input it cannot read.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Lines = dict[str, dict[int, int]]  # coverage as one shape: {file: {line: hit count}}; only executable lines appear
Where = tuple[str, int, int]  # where a mutant's code is: project-relative file, first line, last line


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    capture: str | None = None  # write the step's stdout to this artifact
    timeout: int = 1800
    must_pass: bool = True
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MutationTool:
    """Its report is one `<mutant>: <status>` line per mutant (see harden.py); these say what the report means."""

    artifact: str  # the file the run leaves behind
    how: str  # how to produce it yourself, for the error message
    caught: frozenset[str]  # statuses that mean the tests noticed the mutant
    ignored: frozenset[str]  # statuses of lines that are no mutant at all
    never_ran: frozenset[str]  # statuses a run that did not work leaves on every mutant
    empty: str  # the error for a report without mutants
    broken: str  # the error for a report where no mutant ever ran
    locate: Callable[[list[str], Path], dict[str, Where]]  # (mutants, project root) -> where each one's code is


@dataclass(frozen=True)
class Language:
    suffixes: tuple[str, ...]  # source files
    markers: tuple[str, ...]  # files (globs) whose presence says "this project uses the language" (for `init`)
    tests: str  # regex for test files: the clean gate does not hold them to the CRAP limit
    pragma: str  # regex for the comments that exclude code from the gates
    coverage_file: str  # the artifact the clean gate reads
    image: str  # the image of an OpenShell sandbox (isolation is optional; commands otherwise run on this machine)
    artifacts: tuple[str, ...]  # every file the gates read; `stamp` binds these
    # (safe src path, project dir, output dir, mutation tool, source files in scope) -> the fixed commands.
    # No files in scope means all of them; with some, the mutation step may skip every other file.
    steps: Callable[[str, str, str, str, tuple[str, ...]], list[Step]]
    read_coverage: Callable[[str], Lines]
    mutation: dict[str, MutationTool]  # by the name `[mutation] tool` takes; core defaults to "mutmut"
    imports: Callable[[str, list[str]], list[tuple[int, str]]]  # (source, its package) -> (line, imported module)
    comments: Callable[[str], list[tuple[int, str]]]  # source -> (line, comment text); real comments only
    config_excludes: Callable[[Path], list[str]]  # exclusion settings in the repo's own tool config
    template: Callable[[Path], str]  # starter gauntlet.toml for the project at this root
