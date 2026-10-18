"""Mutation testing of a CMake project with universalmutator, run by gauntlet inside the sandbox (python3 -P, stdlib
only). The repository chooses nothing here: which files are mutated, the rules (universalmutator's built-in ones), the
commands and the limits are all fixed in this file or passed in by `runner`.

For every source file: `mutate` makes the mutants that still build, then `analyze_mutants` puts each one in place,
rebuilds in a separate build directory and runs ctest. A failing ctest (or a test timeout) kills the mutant. The result
is one JSON report: {"mutants": [{"file", "line", "mutation", "status": "killed" | "survived"}]}.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

TEST_TIMEOUT = 120  # seconds ctest gives one test; a mutant that makes a test hang is killed
MUTANT_TIMEOUT = 1800  # seconds analyze_mutants gives one rebuild + test run
SKIP_DIRS = {".git"}  # anywhere
OUT_DIR = ".gauntlet-out"  # our own output: skipped at the top level only, a nested one is project code
LABEL_LIMIT = 80


def _kept_dirs(dirs: list[str], top: bool) -> list[str]:
    return sorted(d for d in dirs if d not in SKIP_DIRS and not (top and d == OUT_DIR))


def sources(root: Path, suffixes: tuple[str, ...], tests: str) -> list[str]:
    """Project-relative source files to mutate: the language's suffixes, minus its test files."""
    found: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = _kept_dirs(dirs, Path(dirpath) == root)
        rels = (Path(dirpath, n).relative_to(root).as_posix() for n in sorted(names))
        found += [r for r in rels if r.endswith(suffixes) and not re.search(tests, r)]
    return found


def run(argv: list[str], cwd: Path) -> None:
    done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        tail = " | ".join(p for p in (done.stderr.strip(), done.stdout.strip()) if p)[-1500:]
        raise SystemExit(f"{Path(argv[0]).name} failed (exit {done.returncode}): {tail}")


def module(name: str, *args: str) -> list[str]:
    return [sys.executable, "-P", "-m", f"universalmutator.{name}", *args]


def build_command(cmake: str, build: str) -> str:
    return f"{shlex.quote(cmake)} --build {shlex.quote(build)} >/dev/null 2>&1"


def test_command(ctest: str, build: str) -> str:
    return f"{shlex.quote(ctest)} --test-dir {shlex.quote(build)} --timeout {TEST_TIMEOUT} >/dev/null 2>&1"


def change(original: str, mutant: Path) -> tuple[int, str]:
    """The line a mutant changed and what it changed it to."""
    after = mutant.read_text().splitlines()
    for number, (old, new) in enumerate(zip(original.splitlines(), after, strict=False), 1):
        if old != new:
            return number, f"{old.strip()[:LABEL_LIMIT]} -> {new.strip()[:LABEL_LIMIT]}"
    raise SystemExit(f"{mutant.name} does not differ from its source")


def names(path: Path) -> set[str]:
    return set(path.read_text().split())


def analyse(rel: str, work: Path, root: Path, build: str, test: str) -> list[dict[str, object]]:
    """Mutate one file and run its mutants. Every mutant must end up killed or survived: a partial run is an error."""
    source = root / rel
    original = source.read_bytes()
    work.mkdir(parents=True)
    # A build that fails is NOT a kill (exit 0 = survived): genmutants already left out the mutants that do not build.
    both = f"{build} || exit 0; {test}"
    try:
        run(module("genmutants", str(source), "--cmd", build, "--mutantDir", str(work)), work)
        run(module("analyze", str(source), both, "--mutantDir", str(work), "--noShuffle",
                   "--timeout", str(MUTANT_TIMEOUT)), work)  # fmt: skip
    finally:
        source.write_bytes(original)  # analyze_mutants restores it too; this is the backstop
    killed, survived = names(work / "killed.txt"), names(work / "notkilled.txt")
    made = {p.name for p in work.glob(f"*.mutant.*{source.suffix}")}
    if made != killed | survived:
        raise SystemExit(f"{rel}: {len(made)} mutants made, {len(killed | survived)} analysed: partial run")
    rows: list[dict[str, object]] = []
    for name in sorted(made):
        line, what = change(original.decode(), work / name)
        rows.append({"file": rel, "line": line, "mutation": what, "status": "killed" if name in killed else "survived"})
    return rows


def main(argv: list[str]) -> int:
    root_arg, out_arg, report, suffixes, tests, *flags = argv
    root, out = Path(root_arg), Path(out_arg)
    cmake, ctest, build = str(out / "py/bin/cmake"), str(out / "py/bin/ctest"), str(out / "mutbuild")
    shutil.rmtree(out / "mutwork", ignore_errors=True)
    shutil.rmtree(build, ignore_errors=True)
    run([cmake, "-S", str(root), "-B", build, "-DCMAKE_BUILD_TYPE=Debug", *flags], root)
    builds, tests_pass = build_command(cmake, build), test_command(ctest, build)
    run(["sh", "-c", f"{builds} && {tests_pass}"], root)  # the unmutated project must pass, or every mutant would die
    rows: list[dict[str, object]] = []
    for index, rel in enumerate(sources(root, tuple(suffixes.split(",")), tests)):
        rows += analyse(rel, out / "mutwork" / str(index), root, builds, tests_pass)
    Path(report).write_text(json.dumps({"mutants": rows}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
