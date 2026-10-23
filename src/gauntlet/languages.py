"""Every supported language is one row. Adding a language starts here."""

from dataclasses import dataclass
from pathlib import Path

ConfigScan = tuple[str, str]  # (file glob, regex a line must match; empty: the file's existence is the finding)


@dataclass(frozen=True)
class Language:
    suffixes: tuple[str, ...]  # source files
    markers: tuple[str, ...]  # files (globs) whose presence says "this project uses the language" (for `init`)
    tests: str  # regex for test files: the clean gate does not hold them to the CRAP limit
    pragma: str  # regex for the comments that exclude code from the gates
    coverage_file: str  # the artifact the clean gate reads ...
    coverage_format: str  # ... and its format (a key of linecov.PARSERS)
    sdk: str  # the Canonical Workshop SDK
    image: str  # the default Docker image (the policy can override it per language)
    artifacts: tuple[str, ...]  # every file the gates read; `stamp` binds these
    optional: tuple[str, ...] = ()  # artifacts `run` may not produce (their tool is allowed to fail)
    config_scan: tuple[ConfigScan, ...] = ()  # build settings that can hide code from coverage
    parse_as: str = ""  # lizard has no reader for the suffixes: parse them with this other language's reader


_MSBUILD_HIDES = (  # project settings that steer or filter coverlet, or that a repo uses to override our own
    r"RunSettingsFilePath|VSTestSetting|VSTestCLIRunSettings|TreatAsLocalProperty|ExcludeByFile|ExcludeByAttribute"
    r"|<Exclude>|<Include>|IncludeTestAssembly|SkipAutoProps"
)

CPP_SUFFIXES = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp")
CPP_TESTS = r"^tests?/"  # only the top-level test dir: a name inside the source tree cannot opt out
CPP_PRAGMA = (
    r"\b[GL]COVR?_EXCL_(?:LINE|START|STOP|BR_LINE|BR_START|BR_STOP|BR_SOURCE|FUNCTION)\b|\bNOLINT"
    r"|#\s*pragma\s+(?:GCC|clang)\s+diagnostic\b|__attribute__\s*\(\(\s*no_(?:profile_)?instrument_function\b"
    r"|\bmull-(?:off|ignore(?:-next)?)\b"  # Mull's comments that hide code from the mutation run
    # universalmutator skips a line with DO_NOT_MUTATE, a @BEGIN/END_TEST_CODE block, and any line that opens
    # or closes a /* comment (so code sharing that line is never mutated)
    r"|\bDO_NOT_MUTATE\b|@(?:BEGIN|END)_TEST_CODE\b|\S.*?/\*|\*/\s*\S"
)
CPP_CONFIG_SCAN: tuple[ConfigScan, ...] = (
    ("mull.yml", ""),  # Mull could mutate less; gauntlet passes its own config
    ("*.rules", ""),  # universalmutator rule files: the sandbox run uses only its built-in rules
    ("custom_handler.py", ""),  # universalmutator imports it if it finds it: the sandbox run does not
)

TABLE: dict[str, Language] = {
    "python": Language(
        suffixes=(".py",),
        markers=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        tests=r"^(tests?/|conftest\.py$)",  # only the top-level test dir: a name inside src/ cannot opt out
        pragma=r"#\s*(?:pragma:\s*no\s+(?:mutate|cover)|nosec)\b",
        coverage_file="coverage.json",
        coverage_format="coveragepy",
        sdk="uv",
        image="ghcr.io/astral-sh/uv:python3.12-bookworm",
        artifacts=("coverage.json", "mutmut-results.txt"),
    ),
    "go": Language(
        suffixes=(".go",),
        markers=("go.mod",),
        tests=r"_test\.go$",
        pragma=r"//\s*nolint\b",
        coverage_file="cover.out",
        coverage_format="gocover",
        sdk="go",
        image="golang:1.27",
        artifacts=("cover.out", "imports.txt", "mutation.json"),
        optional=("mutation.json",),
    ),
}
TABLE["javascript"] = Language(
    suffixes=(".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"),
    markers=("package.json",),
    tests=r"^(tests?|__tests__)/",
    pragma=(
        r"(?://|/\*)\s*(?:istanbul ignore|c8 ignore|v8 ignore|node:coverage\s+(?:ignore|disable)"
        r"|eslint-disable|@ts-ignore|@ts-nocheck|(?i:stryker\s*disable))\b"  # Stryker: disable [next-line|all|...]
    ),
    coverage_file="lcov.info",
    coverage_format="lcov",
    sdk="node",
    image="node:22-bookworm",
    artifacts=("lcov.info", "stryker.json"),
    config_scan=(
        (".c8rc*", ""),
        (".nycrc*", ""),
        ("*c8.config.*", ""),
        ("*nyc.config.*", ""),
        (".mocharc*", ""),
        ("stryker.conf.*", ""),  # Stryker could mutate less; gauntlet passes its own config, but reports the file
        (".stryker*", ""),
        ("package.json", r'"(?:c8|nyc|stryker)"\s*:'),
    ),
)
TABLE["csharp"] = Language(
    suffixes=(".cs",),
    markers=("*.sln", "*.csproj"),
    tests=r"^[Tt]ests?/",  # top-level only: a Tests directory inside src/ cannot opt out
    pragma=(  # every hint coverlet and Stryker.NET honour: attributes (by name), pragmas, codecov and Stryker comments
        r"\b(?:ExcludeFromCodeCoverage|ExcludeFromCoverage|GeneratedCode|CompilerGenerated)(?:Attribute)?\b"
        r"|#\s*pragma\s+warning\s+disable\b|//\s*codecov\b|//\s*(?i:stryker\s*(?:disable|restore))\b"
    ),
    coverage_file="coverage.cobertura.xml",
    coverage_format="cobertura",
    sdk="dotnet",
    image="mcr.microsoft.com/dotnet/sdk:8.0.426",
    artifacts=("coverage.cobertura.xml", "stryker-report.json"),
    config_scan=(
        ("*.runsettings", ""),
        ("*.testsettings", ""),
        ("*.rsp", ""),
        ("stryker-config.*", ""),  # Stryker.NET's own settings; also under .config/
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
        r"|@(?:\w+\.)*(?:SuppressWarnings|DoNotMutate|CoverageIgnore)\b"  # DoNotMutate: PIT skips the annotated code
        r"|//\s*(?:NOSONAR|NOPMD|CHECKSTYLE:OFF|@formatter:off)\b"
    ),
    coverage_file="jacoco.xml",
    coverage_format="jacoco",
    sdk="java",
    image="maven:3.9-eclipse-temurin-21",
    artifacts=("jacoco.xml", "mutations.xml"),
    optional=("mutations.xml",),
    config_scan=(  # the pom's own JaCoCo/Surefire settings and source layout, and Maven's project-level overrides
        (
            "pom.xml",
            r"jacoco|pitest|targetClasses|withHistory|avoidCallsTo|sourceDirectory|testSourceDirectory|skipTests|maven\.test\.skip|testFailureIgnore",
        ),
        (".mvn/*", ""),
    ),
)
TABLE["rust"] = Language(
    suffixes=(".rs",),
    markers=("Cargo.toml",),
    tests=r"^tests/",  # inline `#[cfg(test)]` modules live in src/ and are measured as source
    pragma=(  # attributes that hide code from llvm-cov or the linters; a cfg_attr left open on its line is flagged too
        r"#\s*!?\s*\[\s*(?:coverage\s*\(\s*off|no_coverage|allow\s*\(|expect\s*\(|rustfmt\s*::\s*skip"
        r"|automatically_derived|(?:cfg_attr\s*\(.*)?(?:::\s*)?mutants\s*::\s*skip|cfg(?:_attr)?\s*\(.*coverage"
        r"|cfg_attr\s*\((?:.*(?:allow\s*\(|expect\s*\(|rustfmt\s*::\s*skip)|(?!.*\])))"
        r"|//\s*LCOV_EXCL_(?:LINE|START|STOP|BR_LINE|BR_START|BR_STOP)\b"
    ),
    coverage_file="lcov.info",
    coverage_format="lcov",
    sdk="rust",
    image="rust:1.93-bookworm",
    artifacts=("lcov.info", "mutants-outcomes.json"),
    config_scan=(  # repo-level cargo and toolchain settings change how the measured build is compiled
        (".cargo/config*", ""),
        ("rust-toolchain*", ""),
        ("Cargo.toml", r"rustflags|check-cfg"),
        ("mutants.toml", ""),  # cargo-mutants filters (also .cargo/mutants.toml); the sandbox run ignores them
    ),
)
TABLE["cpp"] = Language(
    suffixes=CPP_SUFFIXES,
    markers=("CMakeLists.txt", "Makefile", "meson.build"),
    tests=CPP_TESTS,
    pragma=CPP_PRAGMA,
    coverage_file="lcov.info",
    coverage_format="lcov",
    sdk="cpp",
    image="gcc:14.3-bookworm",
    artifacts=("lcov.info", "cpp-mutants.json"),
    config_scan=CPP_CONFIG_SCAN,
)
TABLE["cpp-clang"] = Language(  # clang coverage and Mull mutation; chosen with `language = "cpp-clang"`, never detected
    suffixes=CPP_SUFFIXES,
    markers=(),
    tests=CPP_TESTS,
    pragma=CPP_PRAGMA,
    coverage_file="lcov.info",
    coverage_format="lcov",
    sdk="cpp",
    image="silkeh/clang:21-trixie@sha256:7cb6d48fa9882b0956f09e6e722f38c9cef11fb676f60db2b9ce612f4ff9e58d",
    artifacts=("lcov.info", "mull-report.json"),
    config_scan=CPP_CONFIG_SCAN,
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
    sdk="dart",
    image="dart:3.9.4",
    artifacts=("lcov.info",),
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
