"""A private copy of the working tree (tracked + untracked, minus ignored) for the sandbox to work in.

The sandbox never sees the real checkout: it cannot edit gauntlet's own sandbox definition or the source mid-run.
"""

import shutil
from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.provenance import git_output
from gauntlet.safefs import inside

MAX_BYTES = 500_000_000
MAX_FILES = 200_000


def _listed(source: Path) -> list[str]:
    raw = git_output(source, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({n.decode() for n in raw.split(b"\0") if n})


def snapshot(source: Path, dest: Path, max_bytes: int = MAX_BYTES, max_files: int = MAX_FILES) -> int:
    if dest.exists() and any(dest.iterdir()):
        raise GauntletError(f"{dest} is not empty")
    names = _listed(source)
    if len(names) > max_files:
        raise GauntletError(f"{source} has more than {max_files} files")
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    dest.chmod(0o700)
    total, copied = 0, 0
    for name in names:
        if not (source / name).exists():  # tracked but deleted in the working tree
            continue
        src = inside(source, name)  # resolves symlinks; refuses any that leave the repo
        total += src.stat().st_size
        if total > max_bytes:
            raise GauntletError(f"{source} is over the {max_bytes} byte limit")
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied += 1
    return copied
