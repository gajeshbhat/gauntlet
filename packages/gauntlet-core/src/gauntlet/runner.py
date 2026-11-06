"""Produce gate artifacts by running fixed, pinned commands inside a sandbox on a private snapshot of the repo.

Nothing the repository contains chooses what runs: commands, tool versions and output names are defined here.
Target code (its tests, mutation runs) executes only in the sandbox; its outputs are copied out and stamped on the host.
"""

import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from gauntlet import languages
from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.plugin import Step
from gauntlet.provenance import excluded, fingerprint, stamp
from gauntlet.safefs import MAX_ARTIFACT_BYTES
from gauntlet.snapshot import snapshot
from gauntlet_sandbox import PROJECT_DIR, ExecResult, Sandbox

OUT_DIR = ".gauntlet-out"
IN_SANDBOX = f"{PROJECT_DIR}/{OUT_DIR}"
PATH_OK = re.compile(r"^(\.|[A-Za-z0-9_][A-Za-z0-9_./-]*)$")


def _safe_path(value: str) -> str:
    if not PATH_OK.match(value) or ".." in value.split("/"):
        raise GauntletError(f"unsafe path {value!r}")
    return value


def steps(cfg: Config) -> list[Step]:
    return languages.get(cfg.language).steps(_safe_path(cfg.src), IN_SANDBOX, cfg.mutation_tool)


def output_tail(done: ExecResult) -> str:
    """The end of what a failed command printed: stderr and stdout, whichever have content."""
    return " | ".join(part for part in (done.stderr.strip(), done.stdout.strip()) if part)[-2000:]


def _stale(cfg: Config) -> tuple[str, ...]:
    return (f"{IN_SANDBOX}/{languages.get(cfg.language).mutation[cfg.mutation_tool].artifact}",)


def _clear(box: Sandbox, stale: tuple[str, ...]) -> None:
    removal = box.exec(["rm", "-rf", "--", *stale], {}, 60)
    if removal.code != 0:
        raise GauntletError(f"could not clear the old mutation report: {output_tail(removal)}")


def _run_steps(box: Sandbox, plan: list[Step], stale: tuple[str, ...] = ()) -> dict[str, bytes]:
    """Run the plan. `stale` (the mutation report and the intermediate files the copy steps read) is removed by the
    sandbox itself right before the mutation step: a file the tests left behind can never stand in for the report of a
    mutation run that crashed or timed out, and the host never touches a path the tests could have turned into a
    symlink."""
    captured: dict[str, bytes] = {}
    for step in plan:
        if stale and step.name == "mutation":
            _clear(box, stale)
        done = box.exec(step.argv, dict(step.env), step.timeout)
        if done.code != 0 and step.must_pass:
            raise GauntletError(f"step {step.name!r} failed (exit {done.code}): {output_tail(done)}")
        if step.capture and done.stdout:
            captured[step.capture] = done.stdout.encode()
            _check_size(step.capture, captured[step.capture])
    return captured


def _check_size(name: str, data: bytes) -> None:
    if len(data) > MAX_ARTIFACT_BYTES:
        raise GauntletError(f"{name} is {len(data)} bytes, over the {MAX_ARTIFACT_BYTES} byte limit")


def _read_artifact(path: Path) -> bytes | None:
    if path.is_symlink():
        raise GauntletError(f"{path.name} is a symlink")
    data = path.read_bytes() if path.is_file() else None
    if data is not None:
        _check_size(path.name, data)
    return data


def _written(snap: Path, names: list[str]) -> dict[str, bytes]:
    """The artifacts the sandbox wrote to its output directory."""
    if (snap / OUT_DIR).is_symlink():  # the tests swapped the output directory for a link to somewhere on the host
        raise GauntletError(f"{OUT_DIR} is a symlink")
    found = {name: _read_artifact(snap / OUT_DIR / name) for name in names}
    return {name: data for name, data in found.items() if data is not None}


def _collect(snap: Path, language: str, plan: list[Step], captured: dict[str, bytes]) -> dict[str, bytes]:
    """The row's artifacts: a step's captured stdout, else the file the sandbox wrote. A file never stands in for a
    captured artifact, so the tests cannot forge one by leaving it in the output directory."""
    row = languages.get(language)
    stdout = {step.capture for step in plan}
    found = {**_written(snap, [n for n in row.artifacts if n not in stdout]), **captured}
    missing = [n for n in row.artifacts if n not in found]
    if missing:
        raise GauntletError(f"the sandbox did not produce {', '.join(missing)}")
    return found


def produce(source: Path, cfg: Config, out: Path, make_sandbox: Callable[[Path], Sandbox]) -> list[str]:
    """Run the pipeline in a sandbox; leave stamped artifacts in `out`. Returns the artifact names."""
    skip = excluded(out, source, ())
    before = fingerprint(source, skip)
    with tempfile.TemporaryDirectory(prefix="gauntlet-") as tmp:
        snap = Path(tmp) / "project"
        snapshot(source, snap)
        (snap / OUT_DIR).mkdir()
        plan = steps(cfg)
        box = make_sandbox(snap)
        box.ensure()
        try:
            captured = _run_steps(box, plan, _stale(cfg))
        finally:
            box.remove()
        found = _collect(snap, cfg.language, plan, captured)
    if fingerprint(source, skip) != before:
        raise GauntletError("source changed while the gauntlet ran; rerun it")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in found.items():
        (out / name).write_bytes(data)
    stamp(out, source, sorted(found))
    return sorted(found)
