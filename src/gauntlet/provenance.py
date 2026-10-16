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

MANIFEST = "gauntlet-manifest.json"
SAFE_GIT = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]
GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
}


def git_output(source: Path, *args: str) -> bytes:
    done = subprocess.run(
        ["git", *SAFE_GIT, "-C", str(source), *args],
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
    )
    if done.returncode != 0:
        raise ValueError(f"{source} is not a git repository (or git refused to read it)")
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


def fingerprint(source: Path, exclude: tuple[str, ...] = ()) -> str:
    """Hash of HEAD plus the state of every tracked and untracked (non-ignored) file, minus the excluded paths."""
    skip = [f":(exclude){p}" for p in exclude]
    h = hashlib.sha256()
    h.update(git_output(source, "rev-parse", "HEAD"))
    listed = git_output(source, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".", *skip)
    for name in sorted(set(filter(None, listed.split(b"\0")))):
        h.update(name + b"\0" + _entry(source / name.decode()) + b"\0")
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
        raise ValueError(
            f"{art} is not stamped (no {MANIFEST}); run `gauntlet stamp` right after producing the artifacts"
        )
    manifest: dict[str, Any] = json.loads(path.read_text())
    for name in files:
        if name not in manifest["files"]:
            raise ValueError(f"{name} is not covered by the manifest")
        if _digest(art / name) != manifest["files"][name]:
            raise ValueError(f"{name} changed since it was stamped")
    if fingerprint(source, excluded(art, source, exclude)) != manifest["fingerprint"]:
        raise ValueError("artifacts are stale: the source changed since they were stamped")
    return manifest
