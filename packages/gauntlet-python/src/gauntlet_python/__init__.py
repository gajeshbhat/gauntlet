"""The Python language plugin: registered as the `python` entry point of the `gauntlet.languages` group."""

from pathlib import Path

from gauntlet.plugin import Language, MutationTool

from .cosmic import check as check_cosmic
from .coverage import coveragepy
from .excludes import comments, config_excludes
from .imports import imports_at
from .mutmut import check as check_mutmut
from .steps import steps

TEMPLATE = """language = "python"
src = "{src}"

# Optional: imports may only point down this list (outermost layer first), each a dotted module prefix.
# [layers]
# order = ["app.web", "app.service", "app.domain"]
"""

NOT_SOURCE = {"tests", "test", "docs", "doc", "examples", "benchmarks", "scripts", "build", "dist"}


def source_dir(root: Path) -> str:
    """`src` for a src layout; the one top-level package of a flat layout; else the project root."""
    if (root / "src").is_dir():
        return "src"
    packages = [p.name for p in sorted(root.iterdir()) if (p / "__init__.py").is_file() and p.name not in NOT_SOURCE]
    return packages[0] if len(packages) == 1 else "."


LANGUAGE = Language(
    suffixes=(".py",),
    markers=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
    tests=r"^(tests?/|conftest\.py$)",  # only the top-level test dir: a name inside src/ cannot opt out
    # coverage.py's default exclude regex (case-insensitive, optional colon) plus `no branch`, mutmut and bandit
    pragma=r"#\s*(?i:pragma)[:\s]?\s*(?i:no)\s*(?i:cover|branch)|#\s*pragma:\s*no\s+mutate\b|#\s*nosec\b",
    coverage_file="coverage.json",
    sdk="uv",
    image="ghcr.io/astral-sh/uv:python3.12-bookworm",
    artifacts=("coverage.json", "mutmut-results.txt"),
    steps=steps,
    read_coverage=coveragepy,
    mutation={  # both write the same artifact name; the name predates the second tool
        "mutmut": MutationTool(
            "mutmut-results.txt",
            "mutmut run && mutmut results --all true > mutmut-results.txt (or: gauntlet run)",
            check_mutmut,
        ),
        "cosmic-ray": MutationTool(
            "mutmut-results.txt", 'set [mutation] tool = "cosmic-ray" and run: gauntlet run', check_cosmic
        ),
    },
    imports=imports_at,
    comments=comments,
    config_excludes=config_excludes,
    template=lambda root: TEMPLATE.format(src=source_dir(root)),
)
