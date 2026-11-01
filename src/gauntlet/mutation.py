"""The mutation tool of each language: where its report lands and how it is read. The tool runs in the sandbox
(`gauntlet run`)."""

from collections.abc import Callable
from dataclasses import dataclass

from gauntlet import harden
from gauntlet.config import Config
from gauntlet.results import Mutation
from gauntlet.scope import Scope


@dataclass(frozen=True)
class Tool:
    artifact: str  # the file the sandbox run leaves behind
    how: str  # how to produce it yourself, for the error message
    read: Callable[[str, Scope, Config], Mutation]


TOOLS: dict[str, Tool] = {
    "python": Tool(
        "mutmut-results.txt",
        "mutmut run && mutmut results --all true > mutmut-results.txt (or: gauntlet run)",
        lambda text, scope, cfg: harden.check(text),  # noqa: ARG005
    ),
}
