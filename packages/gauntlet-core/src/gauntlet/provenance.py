"""Bind gate inputs to the exact source they were produced from, so a stale green artifact cannot pass.

`stamp` records the source fingerprint and a hash of every artifact; `verify` refuses anything that changed since.
Git is only asked for names (HEAD, tracked and untracked paths); file contents are hashed here, so no diff, textconv or
clean/smudge filter ever runs, whatever the repository's config or .gitattributes say.
"""

import hashlib
import json
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gauntlet.errors import GauntletError

MANIFEST = "gauntlet-manifest.json"
SAFE_GIT = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]
GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
}


def own_git_dir(source: Path) -> Path:
    """Where gauntlet keeps the repository of a directory an agent writes into (see `git_output`)."""
    base = source.resolve()  # "." has no name to hang a suffix on
    return base.with_name(base.name + ".gauntlet-git")


def git_output(source: Path, *args: str) -> bytes:
    """Run git on `source`. If gauntlet keeps its own git dir for it, that one is used and `source/.git` is ignored.

    An agent that can write to `source` can plant a clean filter in `.git/config` (plus a `.gitattributes`) or edit
    `.git/info/exclude`, to run a command on the host at the next `git add` or to hide files from the listing.
    """
    own = own_git_dir(source)
    explicit = [f"--git-dir={own}", f"--work-tree={source}"] if own.is_dir() else []
    done = subprocess.run(
        ["git", *SAFE_GIT, *explicit, "-C", str(source), *args],
        capture_output=True,
        env=GIT_ENV,
    )
    if done.returncode != 0:
        raise GauntletError(f"{source} is not a git repository (or git refused to read it)")
    return done.stdout


def _digest(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _entry(path: Path) -> bytes:
    """What identifies a file's state: its type, executable bit and bytes (a symlink's own target, never followed)."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return b"deleted"
    executable = b"x" if info.st_mode & stat.S_IXUSR else b"-"
    if stat.S_ISLNK(info.st_mode):
        return b"l" + executable + os.readlink(path).encode()
    if stat.S_ISDIR(info.st_mode):  # a submodule or embedded repository: fingerprint it too
        return b"d" + fingerprint(path).encode() if (path / ".git").exists() else b"d"  # empty: just that it is there
    return b"f" + executable + _digest(path).encode()


def listed(source: Path, exclude: tuple[str, ...] = ()) -> list[str]:
    """Sorted names of the tracked and untracked (non-ignored) files, minus the excluded paths."""
    skip = [f":(exclude){p}" for p in exclude]
    raw = git_output(source, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".", *skip)
    return sorted({n.decode() for n in raw.split(b"\0") if n})


def source_files(source: Path, suffixes: tuple[str, ...]) -> list[str]:
    """The listed regular files ending in one of `suffixes`: the same set the fingerprint and the snapshot cover.

    Taking names from git, not from a directory walk, leaves nothing to hide in a folder called `venv` or `vendor`.
    """
    return [n for n in listed(source) if n.endswith(suffixes) and (source / n).is_file()]


def fingerprint(source: Path, exclude: tuple[str, ...] = ()) -> str:
    """Hash of HEAD plus the state of every tracked and untracked (non-ignored) file, minus the excluded paths."""
    h = hashlib.sha256()
    h.update(git_output(source, "rev-parse", "HEAD"))
    for name in listed(source, exclude):
        h.update(name.encode() + b"\0" + _entry(source / name) + b"\0")
    return h.hexdigest()


def excluded(art: Path, source: Path, exclude: tuple[str, ...]) -> tuple[str, ...]:
    """The artifacts directory (or, at the source root, just the manifest) never counts as source."""
    base, folder = source.resolve(), art.resolve()
    if not folder.is_relative_to(base):
        return exclude
    rel = folder.relative_to(base)
    return (*exclude, str(rel if rel.parts else MANIFEST))


def stamp(art: Path, source: Path, files: list[str], exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    missing = [f for f in files if not (art / f).is_file()]
    if missing:
        raise FileNotFoundError(f"cannot stamp, missing artifact(s): {', '.join(missing)} in {art}")
    manifest: dict[str, Any] = {
        "fingerprint": fingerprint(source, excluded(art, source, exclude)),
        "files": {f: _digest(art / f) for f in files},
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (art / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify(art: Path, source: Path, files: list[str], exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    path = art / MANIFEST
    if not path.is_file():
        raise GauntletError(
            f"{art} is not stamped (no {MANIFEST}); run `gauntlet stamp` right after producing the artifacts"
        )
    manifest: dict[str, Any] = json.loads(path.read_text())
    for name in files:
        if name not in manifest["files"]:
            raise GauntletError(f"{name} is not covered by the manifest")
        if _digest(art / name) != manifest["files"][name]:
            raise GauntletError(f"{name} changed since it was stamped")
    if fingerprint(source, excluded(art, source, exclude)) != manifest["fingerprint"]:
        raise GauntletError("artifacts are stale: the source changed since they were stamped")
    return manifest
