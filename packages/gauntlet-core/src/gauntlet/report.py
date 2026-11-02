"""EVIDENCE.md: what ran, against exactly which source, under which rules, and what it cannot show."""

from collections.abc import Sequence
from importlib.metadata import version

from gauntlet.policy import Policy
from gauntlet.results import GateResult

LIMITS = (
    "- The gates measure the code against the configured constraints; they cannot show those constraints are complete.",
    "- Tests run in the sandbox can forge coverage or mutation results; it protects the host, not the numbers.",
    "- Mutation testing samples the mutants its tool generates; a surviving or missing mutant is no proof either way.",
    "- A human should read the spec the tests encode, not only this report.",
)


def _row(r: GateResult) -> str:
    return f"| {r.gate} | {'PASS' if r.ok else 'FAIL'} | {r.summary.replace('|', chr(92) + '|')} |"


def render(
    results: Sequence[GateResult],
    *,
    language: str,
    fingerprint: str,
    config_sha256: str,
    policy: Policy,
    created: str,
    command: str,
) -> str:
    overall = "PASS" if all(r.ok for r in results) else "FAIL"
    lines = [
        "# Evidence report",
        "",
        f"Generated {created} by gauntlet {version('gauntlet-core')}.",
        "",
        f"- Language: {language}",
        f"- Source fingerprint: `{fingerprint}`",
        f"- gauntlet.toml sha256: `{config_sha256}`",
        f"- Policy: crap ceiling {policy.crap_ceiling}, mutation floor {policy.mutation_floor}, "
        f"exclusion budget {policy.max_exclusions}",
        "",
        "## Gates",
        "",
        "| Gate | Result | Summary |",
        "|---|---|---|",
        *[_row(r) for r in results],
        "",
        f"**Overall: {overall}**",
    ]
    for r in results:
        if r.findings:
            lines += ["", f"### {r.gate}", "", *[f"- `{f}`" for f in r.findings]]
    lines += ["", "## What this does not prove", "", *LIMITS, "", "## Reproduce", "", "```", command, "```", ""]
    return "\n".join(lines)
