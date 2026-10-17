"""Every supported language is one row. Adding a language starts here."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Language:
    suffixes: tuple[str, ...]  # source files
    markers: tuple[str, ...]  # files (globs) whose presence says "this project uses the language" (for `init`)
    tests: str  # regex for test files: the clean gate does not hold them to the CRAP limit
    pragma: str  # regex for the comments that exclude code from the gates
    coverage_file: str  # the artifact the clean gate reads ...
    coverage_format: str  # ... and its format (a key of linecov.PARSERS)
    mutation: bool  # a mutation tool is wired; without one `run` reports the harden gate as skipped
    sdk: str  # the Canonical Workshop SDK
    image: str  # the default Docker image (the policy can override it per language)


TABLE: dict[str, Language] = {
    "python": Language(
        suffixes=(".py",),
        markers=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        tests=r"^(tests?/|conftest\.py$)",  # only the top-level test dir: a name inside src/ cannot opt out
        pragma=r"#\s*(?:pragma:\s*no\s+(?:mutate|cover)|nosec)\b",
        coverage_file="coverage.json",
        coverage_format="coveragepy",
        mutation=True,
        sdk="uv",
        image="ghcr.io/astral-sh/uv:python3.12-bookworm",
    ),
    "go": Language(
        suffixes=(".go",),
        markers=("go.mod",),
        tests=r"_test\.go$",
        pragma=r"//\s*nolint\b",
        coverage_file="cover.out",
        coverage_format="gocover",
        mutation=True,
        sdk="go",
        image="golang:1.27",
    ),
}
TABLE["javascript"] = Language(
    suffixes=(".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"),
    markers=("package.json",),
    tests=r"^(tests?|__tests__)/",
    pragma=(
        r"(?://|/\*)\s*(?:istanbul ignore|c8 ignore|v8 ignore|node:coverage\s+(?:ignore|disable)"
        r"|eslint-disable|@ts-ignore|@ts-nocheck)\b"
    ),
    coverage_file="lcov.info",
    coverage_format="lcov",
    mutation=False,
    sdk="node",
    image="node:22-bookworm",
)
TABLE["csharp"] = Language(
    suffixes=(".cs",),
    markers=("*.sln", "*.csproj"),
    tests=r"^[Tt]ests?/",  # top-level only: a Tests directory inside src/ cannot opt out
    pragma=(  # every hint coverlet honours: attributes (by name, any namespace), plus pragmas and codecov comments
        r"\b(?:ExcludeFromCodeCoverage|ExcludeFromCoverage|GeneratedCode|CompilerGenerated)(?:Attribute)?\b"
        r"|#\s*pragma\s+warning\s+disable\b|//\s*codecov\b"
    ),
    coverage_file="coverage.cobertura.xml",
    coverage_format="cobertura",
    mutation=False,
    sdk="dotnet",
    image="mcr.microsoft.com/dotnet/sdk:8.0.426",
)
NAMES = tuple(TABLE)


def get(name: str) -> Language:
    if name not in TABLE:
        raise ValueError(f"unsupported language {name!r}, expected one of {', '.join(NAMES)}")
    return TABLE[name]


def detect(root: Path) -> list[str]:
    """The languages whose marker files exist in `root`, in table order."""
    return [name for name, row in TABLE.items() if any(next(root.glob(m), None) for m in row.markers)]
