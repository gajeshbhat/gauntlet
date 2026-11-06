"""Rules owned by the human, outside the repository the agent can edit.

The repo's `gauntlet.toml` may tighten these limits, never weaken them, and can be pinned by hash so any edit shows up.
"""

import hashlib
import json
import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from gauntlet.config import Config, boolean, choice, integer
from gauntlet.errors import GauntletError

BOOLS = ("allow_config_excludes", "allow_unstamped", "require_pin", "require_arch")
RANGES = {
    "crap_ceiling": (0, 1000),
    "mutation_floor": (0, 100),
    "max_exclusions": (0, 100_000),
}
SANDBOXES = ("local", "openshell")


@dataclass(frozen=True)
class Policy:
    crap_ceiling: int = 8  # repo crap.max may be lower, never higher
    mutation_floor: int = 90  # repo mutation.min_score may be higher, never lower
    max_exclusions: int = 10  # budget of `pragma: no mutate|cover` / nolint / nosec in scope
    allow_config_excludes: bool = False  # coverage `omit` / mutmut `do_not_mutate` in the repo config
    allow_unstamped: bool = False  # accept artifacts with no provenance manifest
    require_pin: bool = False  # refuse a gauntlet.toml that was never pinned
    require_arch: bool = False  # a gauntlet.toml without [layers] fails the check instead of skipping the arch gate
    pins: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    sandbox: str = "local"  # local: on this machine; openshell: in an isolated OpenShell sandbox


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "gauntlet" / "policy.toml"


def _pins(path: Path, data: dict[str, Any]) -> dict[str, str]:
    raw = data.get("pins", {})
    if not isinstance(raw, dict) or not all(isinstance(v, str) and v.startswith("sha256:") for v in raw.values()):  # pyright: ignore[reportUnknownVariableType]
        raise GauntletError(f"{path}: pins must map a config path to 'sha256:<hex>'")
    return {str(k): str(v) for k, v in raw.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def _checked(path: Path, data: dict[str, Any]) -> Policy:
    unknown = sorted(set(data) - {f.name for f in fields(Policy)})
    if unknown:
        raise GauntletError(f"{path}: unknown key(s) {', '.join(unknown)}")
    default = Policy()
    flags: dict[str, Any] = {key: boolean(path, data, key, getattr(default, key)) for key in BOOLS}
    numbers: dict[str, Any] = {k: integer(path, data, k, getattr(default, k), *b) for k, b in RANGES.items()}
    return Policy(
        **flags,
        **numbers,
        pins=_pins(path, data),
        sandbox=choice(path, data, "sandbox", SANDBOXES),
    )


def load(path: Path | None, missing_ok: bool = False) -> Policy:
    """The policy at `path`; the default location when None (absent means defaults)."""
    if path is None:
        path, missing_ok = default_path(), True
    if missing_ok and not path.exists():
        return Policy()
    return _checked(path, tomllib.loads(path.read_text()))


def dump(p: Policy) -> str:
    lines = [f"{f.name} = {json.dumps(getattr(p, f.name))}" for f in fields(p) if f.name != "pins"]  # tuples as lists
    pins = [f"{json.dumps(k)} = {json.dumps(v)}" for k, v in sorted(p.pins.items())]
    return "\n".join([*lines, "", "[pins]", *pins]) + "\n"


def apply(cfg: Config, p: Policy) -> Config:
    """The effective config: the repo's own values, which must not be weaker than the policy's."""
    crap, mutation = p.crap_ceiling, p.mutation_floor
    if "crap" in cfg.explicit:
        if cfg.crap_max > p.crap_ceiling:
            raise GauntletError(f"crap.max = {cfg.crap_max} is weaker than the policy ceiling {p.crap_ceiling}")
        crap = cfg.crap_max
    if "mutation" in cfg.explicit:
        if cfg.mutation_min < p.mutation_floor:
            raise GauntletError(
                f"mutation.min_score = {cfg.mutation_min} is weaker than the policy floor {p.mutation_floor}"
            )
        mutation = cfg.mutation_min
    return replace(cfg, crap_max=crap, mutation_min=mutation)


def _hash(config: Path) -> str:
    return "sha256:" + hashlib.sha256(config.read_bytes()).hexdigest()


def check_pin(p: Policy, config: Path) -> None:
    pinned = p.pins.get(str(config.resolve()))
    if pinned is None:
        if p.require_pin:
            raise GauntletError(f"{config} is not pinned; review it, then run `gauntlet pin`")
        return
    if pinned != _hash(config):
        raise GauntletError(f"{config} changed since it was pinned; review the change, then run `gauntlet pin`")


def pin(p: Policy, config: Path, path: Path) -> Policy:
    pinned = replace(p, pins={**p.pins, str(config.resolve()): _hash(config)})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(dump(pinned))
    tmp.replace(path)
    return pinned
