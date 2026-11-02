"""The Python language plugin: registered as the `python` entry point of the `gauntlet.languages` group."""

from gauntlet.plugin import Language, MutationTool

from .coverage import coveragepy
from .excludes import comments, config_excludes
from .imports import imports_at
from .mutmut import check
from .steps import steps

TEMPLATE = """language = "python"
src = "{src}"

# Optional: imports may only point down this list (outermost layer first), each a dotted module prefix.
# [layers]
# order = ["app.web", "app.service", "app.domain"]
"""

LANGUAGE = Language(
    suffixes=(".py",),
    markers=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
    tests=r"^(tests?/|conftest\.py$)",  # only the top-level test dir: a name inside src/ cannot opt out
    pragma=r"#\s*(?:pragma:\s*no\s+(?:mutate|cover)|nosec)\b",
    coverage_file="coverage.json",
    coverage_format="coveragepy",
    sdk="uv",
    image="ghcr.io/astral-sh/uv:python3.12-bookworm",
    artifacts=("coverage.json", "mutmut-results.txt"),
    steps=steps,
    read_coverage=coveragepy,
    mutation=MutationTool(
        "mutmut-results.txt",
        "mutmut run && mutmut results --all true > mutmut-results.txt (or: gauntlet run)",
        check,
    ),
    imports=imports_at,
    comments=comments,
    config_excludes=config_excludes,
    template=lambda root: TEMPLATE.format(src="src" if (root / "src").is_dir() else "."),
)
