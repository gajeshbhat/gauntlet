"""Rules owned by the human, outside the repository the agent can edit.

The repo's `gauntlet.toml` may tighten these limits, never weaken them, and can be pinned by hash so any edit shows up.
"""

import hashlib
import json
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from gauntlet import languages
from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.names import ENV_NAME, IMAGE, MEMORY

BOOLS = ("allow_config_excludes", "allow_unstamped", "require_pin")
INTS = ("crap_ceiling", "mutation_floor", "max_exclusions")
RANGES = {"agent_timeout": (1, 86_400), "max_rounds": (1, 20)}
LISTS = ("agent_command", "agent_env")
CHOICES = {
    "sandbox": ("auto", "workshop", "docker"),
    "container_cli": ("docker", "podman"),
    "docker_network": ("bridge", "none"),
}
IMAGES = ("docker_image_agent",)  # may be empty (unset)
STRINGS = ("docker_memory",)


@dataclass(frozen=True)
class Policy:
    crap_ceiling: int = 8  # repo crap.max may be lower, never higher
    mutation_floor: int = 90  # repo mutation.min_score may be higher, never lower
    max_exclusions: int = 10  # budget of `pragma: no mutate|cover` / nolint / nosec in scope
    allow_config_excludes: bool = False  # coverage `omit` / mutmut `do_not_mutate` in the repo config
    allow_unstamped: bool = False  # accept artifacts with no provenance manifest
    require_pin: bool = False  # refuse a gauntlet.toml that was never pinned
    pins: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    agent_command: tuple[str, ...] = ()  # argv of the coding agent; the prompt is appended as the last argument
    agent_env: tuple[str, ...] = ()  # names of environment variables passed through to it (never their values)
    agent_timeout: int = 1800
    max_rounds: int = 3  # fixer rounds before the loop gives up
    sandbox: str = (
        "auto"  # workshop (Linux), docker (Linux, macOS, Windows), or auto: workshop if installed, else docker
    )
    container_cli: str = "docker"  # or podman
    docker_network: str = "bridge"  # none cuts the container off (dependencies and agents then cannot download)
    docker_memory: str = ""  # e.g. 4g; empty means no limit
    docker_images: dict[str, str] = field(default_factory=lambda: dict[str, str]())  # language -> image override
    docker_image_agent: str = ""  # an image with your coding agent and the toolchain; see examples/agent.Dockerfile


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "gauntlet" / "policy.toml"


def _check_values(path: Path, data: dict[str, Any]) -> None:
    unknown = sorted(set(data) - {*BOOLS, *INTS, *RANGES, *LISTS, *CHOICES, *IMAGES, *STRINGS, "pins", "docker_images"})
    if unknown:
        raise GauntletError(f"{path}: unknown key(s) {', '.join(unknown)}")
    _check_ints(path, data)
    _check_bools(path, data)
    _check_ranges(path, data)
    _check_lists(path, data)
    _check_choices(path, data)
    _check_memory(path, data)
    _check_images(path, data)


def _check_ints(path: Path, data: dict[str, Any]) -> None:
    for key in INTS:
        value = data.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise GauntletError(f"{path}: {key} must be an integer >= 0")


def _check_bools(path: Path, data: dict[str, Any]) -> None:
    for key in BOOLS:
        if not isinstance(data.get(key, False), bool):
            raise GauntletError(f"{path}: {key} must be true or false")


def _check_ranges(path: Path, data: dict[str, Any]) -> None:
    for key, (lo, hi) in RANGES.items():
        value = data.get(key, lo)
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise GauntletError(f"{path}: {key} must be an integer between {lo} and {hi}")


def _strings(value: Any) -> list[str] | None:
    items: list[Any] = list(value) if isinstance(value, list) else []  # pyright: ignore[reportUnknownArgumentType]
    ok = isinstance(value, list) and all(isinstance(x, str) and x for x in items)
    return [str(x) for x in items] if ok else None


def _check_lists(path: Path, data: dict[str, Any]) -> None:
    if _strings(data.get("agent_command", [])) is None:
        raise GauntletError(f"{path}: agent_command must be a list of non-empty strings")
    env = _strings(data.get("agent_env", []))
    if env is None or not all(ENV_NAME.match(name) for name in env):
        raise GauntletError(f"{path}: agent_env must be a list of environment variable names")


def _check_choices(path: Path, data: dict[str, Any]) -> None:
    for key, allowed in CHOICES.items():
        if data.get(key, allowed[0]) not in allowed:
            raise GauntletError(f"{path}: {key} must be one of {', '.join(allowed)}")


def _check_memory(path: Path, data: dict[str, Any]) -> None:
    memory = data.get("docker_memory", "")
    if not isinstance(memory, str):
        raise GauntletError(f"{path}: docker_memory must be a string")
    if memory and not MEMORY.match(memory):
        raise GauntletError(f"{path}: docker_memory must look like 512m or 4g")


def _check_images(path: Path, data: dict[str, Any]) -> None:
    value = data.get("docker_image_agent", "")
    if not isinstance(value, str) or (value and not IMAGE.match(value)):
        raise GauntletError(f"{path}: docker_image_agent must be a container image name")


def _images(path: Path, data: dict[str, Any]) -> dict[str, str]:
    table: Any = data.get("docker_images", {})
    if not isinstance(table, dict):
        raise GauntletError(f"{path}: docker_images must be a table of language = image")
    for name, image in table.items():  # pyright: ignore[reportUnknownVariableType]
        if name not in languages.TABLE:
            raise GauntletError(
                f"{path}: docker_images has unknown language {name!r}, expected one of {', '.join(languages.NAMES)}"
            )
        if not isinstance(image, str) or not IMAGE.match(image):
            raise GauntletError(f"{path}: docker_images.{name} must be a container image name")
    return {str(k): str(v) for k, v in table.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def _pins(path: Path, data: dict[str, Any]) -> dict[str, str]:
    raw = data.get("pins", {})
    if not isinstance(raw, dict) or not all(isinstance(v, str) and v.startswith("sha256:") for v in raw.values()):  # pyright: ignore[reportUnknownVariableType]
        raise GauntletError(f"{path}: pins must map a config path to 'sha256:<hex>'")
    return {str(k): str(v) for k, v in raw.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def _checked(path: Path, data: dict[str, Any]) -> Policy:
    _check_values(path, data)
    pins, images = _pins(path, data), _images(path, data)
    kw: dict[str, Any] = {
        k: tuple(v) if k in LISTS else v for k, v in data.items() if k not in {"pins", "docker_images"}
    }
    return Policy(**kw, pins=pins, docker_images=images)


def load(path: Path | None, missing_ok: bool = False) -> Policy:
    """The policy at `path`; the default location when None (absent means defaults)."""
    if path is None:
        path, missing_ok = default_path(), True
    if missing_ok and not path.exists():
        return Policy()
    return _checked(path, tomllib.loads(path.read_text()))


def _table(name: str, values: dict[str, str]) -> list[str]:
    return ["", f"[{name}]", *[f"{json.dumps(k)} = {json.dumps(v)}" for k, v in sorted(values.items())]]


def dump(p: Policy) -> str:
    lines = [f"{k} = {getattr(p, k)}" for k in INTS]
    lines += [f"{k} = {str(getattr(p, k)).lower()}" for k in BOOLS]
    lines += [f"{k} = {json.dumps(list(getattr(p, k)))}" for k in LISTS if getattr(p, k)]
    lines += [f"{k} = {getattr(p, k)}" for k in RANGES]
    lines += [f"{k} = {json.dumps(getattr(p, k))}" for k in (*CHOICES, *STRINGS, *IMAGES)]
    return "\n".join([*lines, *_table("docker_images", p.docker_images), *_table("pins", p.pins)]) + "\n"


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
