"""The agent loop: ephemeral agents (one fresh process each) work in a private copy of the repo and hand back a patch.

Specifier writes a spec for a human to approve; Coder implements it; failing gates go to a Fixer that sees only the
failures. The real working tree is never touched: the human reads the patch and the evidence, then applies it.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from gauntlet import spec
from gauntlet.errors import GauntletError
from gauntlet.provenance import git_output, own_git_dir
from gauntlet.results import GateResult
from gauntlet.runner import output_tail
from gauntlet.snapshot import snapshot
from gauntlet_sandbox import ExecResult, Sandbox

CONTROL = (
    "gauntlet.toml", "pyproject.toml", "setup.cfg", "tox.ini", "noxfile.py", "Makefile", "conftest.py", ".coveragerc",
    ".workshop/", ".github/",
)  # fmt: skip
NO_AGENT = "no agent configured: set agent_command in the policy file"
IDENTITY = ["-c", "user.name=gauntlet", "-c", "user.email=gauntlet@localhost", "-c", "commit.gpgsign=false"]


@dataclass(frozen=True)
class Roles:
    specifier: str
    coder: str
    fixer: str


def load_roles() -> Roles:
    base = files("gauntlet") / "roles"
    return Roles(*[(base / f"{name}.md").read_text() for name in ("specifier", "coder", "fixer")])


class Agent:
    """Runs one role as one fresh process: nothing carries over between runs."""

    def __init__(self, sandbox: Sandbox, command: Sequence[str], env: Sequence[str], timeout: int) -> None:
        if not command:
            raise GauntletError(NO_AGENT)
        self.sandbox, self.command, self.env, self.timeout = sandbox, tuple(command), tuple(env), timeout

    def run(self, role: str, task: str) -> ExecResult:
        return self.sandbox.exec([*self.command, f"{role}\n\n{task}"], {name: None for name in self.env}, self.timeout)


def prepare_workspace(source: Path, dest: Path) -> Path:
    snapshot(source, dest)
    own_git_dir(dest).mkdir()  # beside the workspace, outside what the sandbox mounts: the agent cannot edit it
    git_output(dest, "init", "-q", "-b", "main")
    git_output(dest, "add", "-A")
    git_output(dest, *IDENTITY, "commit", "-q", "-m", "baseline", "--allow-empty")
    return dest


OWN_FILES = (":(exclude).workshop/gauntlet-agent.yaml", ":(exclude).workshop.lock")  # not the agent's work


def patch(workspace: Path) -> str:
    git_output(workspace, "add", "-A", "--", ".", *OWN_FILES)
    return git_output(workspace, "diff", "--cached", "HEAD", "--binary", "--no-ext-diff", "--no-textconv").decode()


def control_files(patch_text: str) -> list[str]:
    paths = re.findall(r"^diff --git a/(\S+) b/", patch_text, re.MULTILINE)
    return sorted(p for p in paths if any(p == c or (c.endswith("/") and p.startswith(c)) for c in CONTROL))


def _failed(agent_name: str, done: ExecResult) -> GauntletError:
    return GauntletError(f"{agent_name} failed (exit {done.code}): {output_tail(done)}")


def specify(agent: Agent, roles: Roles, requirement: str, workspace: Path) -> str:
    done = agent.run(roles.specifier, f"Requirement:\n\n{requirement}")
    if done.code != 0:
        raise _failed("specifier", done)
    path = workspace / "spec.feature"
    if not path.is_file():
        raise GauntletError("the specifier did not write spec.feature")
    problems = spec.check(path, workspace, trace=False)
    if problems:
        raise GauntletError("the spec is not valid: " + "; ".join(problems))
    return path.read_text()


@dataclass(frozen=True)
class LoopResult:
    ok: bool
    rounds: int  # fixer rounds used
    results: list[GateResult]


def failures(results: Sequence[GateResult], limit: int = 8000) -> str:
    text = "\n".join(line for r in results if not r.ok for line in (*r.findings, r.summary))
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def implement(
    agent: Agent, roles: Roles, spec_text: str, evaluate: Callable[[], list[GateResult]], max_rounds: int
) -> LoopResult:
    done = agent.run(roles.coder, f"Approved spec:\n\n{spec_text}")
    if done.code != 0:
        raise _failed("coder", done)
    results, rounds = evaluate(), 0
    while not all(r.ok for r in results) and rounds < max_rounds:
        rounds += 1
        done = agent.run(roles.fixer, f"Failures:\n\n{failures(results)}")
        if done.code != 0:
            raise _failed("fixer", done)
        results = evaluate()
    return LoopResult(all(r.ok for r in results), rounds, results)
