from dataclasses import dataclass, field
from typing import Any, NamedTuple


@dataclass(frozen=True)
class GateResult:
    gate: str
    ok: bool
    summary: str
    findings: tuple[str, ...] = ()
    stats: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


class Mutation(NamedTuple):
    pct: float
    survivors: list[str]
    caught: int
    total: int
