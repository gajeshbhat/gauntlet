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
    config_scan: tuple[
        tuple[str, str], ...
    ] = ()  # (file glob, regex) of build settings that can hide code from coverage
    parse_as: str = ""  # lizard has no reader for the suffixes: parse them with this other language's reader


_MSBUILD_HIDES = (  # project settings that steer or filter coverlet, or that a repo uses to override our own
    r"RunSettingsFilePath|VSTestSetting|VSTestCLIRunSettings|TreatAsLocalProperty|ExcludeByFile|ExcludeByAttribute"
    r"|<Exclude>|<Include>|IncludeTestAssembly|SkipAutoProps"
)

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
    config_scan=(
        (".c8rc*", ""),
        (".nycrc*", ""),
        ("c8.config.*", ""),
        (".mocharc*", ""),
        ("package.json", r'"(?:c8|nyc)"\s*:'),
    ),
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
    config_scan=(
        ("*.runsettings", ""),
        ("*.testsettings", ""),
        ("*.csproj", _MSBUILD_HIDES),
        ("*.props", _MSBUILD_HIDES),
        ("*.targets", _MSBUILD_HIDES),
    ),
)
TABLE["java"] = Language(
    suffixes=(".java",),
    markers=("pom.xml", "build.gradle"),
    tests=r"^(tests?|src/test)/",  # Maven never builds src/test into the artifact; a name under src/main cannot opt out
    pragma=(
        r"@(?:\w+\.)*\w*Generated\w*\b"  # JaCoCo skips any annotation whose simple name contains "Generated"
        r"|@(?:\w+\.)*SuppressWarnings\b|//\s*(?:NOSONAR|NOPMD|CHECKSTYLE:OFF|@formatter:off)\b"
    ),
    coverage_file="jacoco.xml",
    coverage_format="jacoco",
    mutation=False,
    sdk="java",
    image="maven:3.9-eclipse-temurin-21",
    config_scan=(  # the pom's own JaCoCo/Surefire settings and source layout, and Maven's project-level overrides
        ("pom.xml", r"jacoco|sourceDirectory|testSourceDirectory|skipTests|maven\.test\.skip|testFailureIgnore"),
        (".mvn/*", ""),
    ),
)
TABLE["rust"] = Language(
    suffixes=(".rs",),
    markers=("Cargo.toml",),
    tests=r"^tests/",  # inline `#[cfg(test)]` modules live in src/ and are measured as source
    pragma=(  # attributes that hide code from llvm-cov or the linters; a cfg_attr left open on its line is flagged too
        r"#\s*!?\s*\[\s*(?:coverage\s*\(\s*off|no_coverage|allow\s*\(|expect\s*\(|rustfmt\s*::\s*skip"
        r"|automatically_derived|cfg(?:_attr)?\s*\([^\]]*coverage"
        r"|cfg_attr\s*\((?:[^\]]*(?:allow\s*\(|expect\s*\(|rustfmt\s*::\s*skip)|[^\]]*$))"
        r"|//\s*LCOV_EXCL_(?:LINE|START|STOP|BR_LINE|BR_START|BR_STOP)\b"
    ),
    coverage_file="lcov.info",
    coverage_format="lcov",
    mutation=False,
    sdk="rust",
    image="rust:1.93-bookworm",
    config_scan=(  # repo-level cargo and toolchain settings change how the measured build is compiled
        (".cargo/config*", ""),
        ("rust-toolchain*", ""),
        ("Cargo.toml", r"rustflags|check-cfg"),
    ),
)
TABLE["cpp"] = Language(
    suffixes=(".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"),
    markers=("CMakeLists.txt", "Makefile", "meson.build"),
    tests=r"^tests?/",  # only the top-level test dir: a name inside the source tree cannot opt out
    pragma=(
        r"\b[GL]COVR?_EXCL_(?:LINE|START|STOP|BR_LINE|BR_START|BR_STOP|BR_SOURCE|FUNCTION)\b|\bNOLINT"
        r"|#\s*pragma\s+GCC\s+diagnostic\b|__attribute__\s*\(\(\s*no_(?:profile_)?instrument_function\b"
    ),
    coverage_file="lcov.info",
    coverage_format="lcov",
    mutation=False,
    sdk="cpp",
    image="gcc:14.3-bookworm",
)
TABLE["dart"] = Language(
    suffixes=(".dart",),
    markers=("pubspec.yaml",),
    tests=r"^test/",  # top-level only: dart test never builds lib/ or bin/, and a name inside lib/ cannot opt out
    pragma=(  # coverage's ignore comments, the analyzer's ignore comments, and dart format's switch
        r"//\s*(?:coverage:ignore-(?:line|start|end|file)|ignore(?:_for_file)?:|dart\s+format\s+(?:off|on))"
    ),
    coverage_file="lcov.info",
    coverage_format="lcov",
    mutation=False,
    sdk="dart",
    image="dart:3.9.4",
    config_scan=(("dart_test.yaml", r"exclude|skip"),),
    parse_as="java",
)
NAMES = tuple(TABLE)


def get(name: str) -> Language:
    if name not in TABLE:
        raise ValueError(f"unsupported language {name!r}, expected one of {', '.join(NAMES)}")
    return TABLE[name]


def detect(root: Path) -> list[str]:
    """The languages whose marker files exist in `root`, in table order."""
    return [name for name, row in TABLE.items() if any(next(root.glob(m), None) for m in row.markers)]
