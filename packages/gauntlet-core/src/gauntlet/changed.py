"""`--changed [REF]`: the lines of the working tree that differ from a commit, as scope entries.

Git is only asked for the old file contents (`cat-file`, which runs no filter, textconv or diff driver, whatever the
repository's config says); the comparison is done here.
"""

import difflib
import re
from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.provenance import git_output, source_files
from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text
from gauntlet.scope import Entry

REF_OK = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./~^@{}-]*$")  # never an option, never two arguments


def _old(source: Path, ref: str, names: list[str]) -> dict[str, str]:
    """What each of `names` held at `ref`; a file that was not there is left out."""
    asked = [n for n in names if "\n" not in n]  # one request per line
    out = git_output(source, "cat-file", "--batch", stdin="".join(f"{ref}:{n}\n" for n in asked).encode())
    found: dict[str, str] = {}
    for name in asked:  # each answer is "<id> <type> <size>\n<content>\n", or "<request> missing\n"
        header, _, out = out.partition(b"\n")
        if not header.endswith(b" missing"):
            size = int(header.split()[-1])
            found[name] = out[:size].decode(errors="replace")
            out = out[size + 1 :]
    return found


def spans(old: str, new: str) -> list[tuple[int, int]]:
    """The line ranges of `new` that are not in `old`; removed lines count as the line that took their place."""
    before, after = old.splitlines(), new.splitlines()
    if before == after:
        return []
    found: list[tuple[int, int]] = []
    # ponytail: difflib is quadratic on a huge rewritten file; shell out to `git diff --no-index` if that ever hurts
    for tag, _, _, lo, hi in difflib.SequenceMatcher(None, before, after).get_opcodes():
        if tag != "equal":
            first = min(lo + 1, max(len(after), 1))
            found.append((first, max(hi, first)))
    return found


def entries(source: Path, ref: str, suffixes: tuple[str, ...]) -> list[Entry]:
    """One entry per changed range of every source file; a file `ref` does not have is in scope as a whole."""
    if not REF_OK.match(ref):
        raise GauntletError(f"bad --changed value {ref!r}: expected a commit, branch or tag")
    try:
        git_output(source, "rev-parse", f"{ref}^{{commit}}")
    except GauntletError:
        raise GauntletError(f"--changed: {ref!r} is not a commit in {source}") from None
    names = source_files(source, suffixes)
    old = _old(source, ref, names)
    found: list[Entry] = []
    for name in names:
        if name not in old:
            found.append((name, None))
            continue
        found += [(name, span) for span in spans(old[name], read_text(inside(source, name), MAX_SOURCE_BYTES))]
    return found
