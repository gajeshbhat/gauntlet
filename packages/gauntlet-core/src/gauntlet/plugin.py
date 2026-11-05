"""The contract a language plugin fills in. Core never names a language; it calls these fields.

A plugin is one `Language` value, registered under the `gauntlet.languages` entry-point group (see languages.py).
Every callable that reads untrusted input raises `GauntletError` for input it cannot read.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gauntlet.results import Mutation

Lines = dict[str, dict[int, int]]  # coverage as one shape: {file: {line: hit count}}; only executable lines appear


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
    artifact: str  # the file the sandbox run leaves behind
    how: str  # how to produce it yourself, for the error message
    read: Callable[[str], Mutation]


@dataclass(frozen=True)
class Language:
    suffixes: tuple[str, ...]  # source files
    markers: tuple[str, ...]  # files (globs) whose presence says "this project uses the language" (for `init`)
    tests: str  # regex for test files: the clean gate does not hold them to the CRAP limit
    pragma: str  # regex for the comments that exclude code from the gates
    coverage_file: str  # the artifact the clean gate reads
    sdk: str  # the Canonical Workshop SDK
    image: str  # the default Docker image (the policy can override it per language)
    artifacts: tuple[str, ...]  # every file the gates read; `stamp` binds these
    steps: Callable[[str, str], list[Step]]  # (safe src path, sandbox output dir) -> the fixed commands to run
    read_coverage: Callable[[str], Lines]
    mutation: MutationTool
    imports: Callable[[str, list[str]], list[tuple[int, str]]]  # (source, its package) -> (line, imported module)
    comments: Callable[[str], list[tuple[int, str]]]  # source -> (line, comment text); real comments only
    config_excludes: Callable[[Path], list[str]]  # exclusion settings in the repo's own tool config
    template: Callable[[Path], str]  # starter gauntlet.toml for the project at this root
