"""Bind gate inputs to the exact source they were produced from, so a stale green artifact cannot pass.

`stamp` records the source fingerprint and a hash of every artifact; `verify` refuses anything that changed since.
Our own git calls ignore repository config that can run commands (diff.external, textconv, fsmonitor).
"""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST = "gauntlet-manifest.json"
SAFE_GIT = ["-c", "core.fsmonitor=false", "-c", "diff.external=", "-c", "core.hooksPath=/dev/null"]


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


def fingerprint(source: Path, exclude: tuple[str, ...] = ()) -> str:
    """Hash of HEAD, every tracked change and every untracked file, minus the excluded paths."""
    skip = [f":(exclude){p}" for p in exclude]
    h = hashlib.sha256()
    h.update(git_output(source, "rev-parse", "HEAD"))
    h.update(git_output(source, "diff", "HEAD", "--binary", "--no-ext-diff", "--no-textconv", "--", ".", *skip))
    untracked = git_output(source, "ls-files", "-z", "--others", "--exclude-standard", "--", ".", *skip)
    for name in sorted(filter(None, untracked.split(b"\0"))):
        h.update(name)
        h.update(_digest(source / name.decode()).encode())
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
