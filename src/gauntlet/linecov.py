"""Line coverage from the formats real tools write, as one shape: {file: {line: hit count}}.

Only executable lines appear in a file's map; a line that is absent is not code that could run.
"""

import json
import re
import xml.etree.ElementTree as ET  # noqa: N817
from collections import defaultdict
from collections.abc import Callable

from gauntlet.errors import GauntletError
from gauntlet.safefs import SKIP_DIRS

MAX_LINES = 5_000_000  # line entries one report may expand to
Lines = dict[str, dict[int, int]]
GO_BLOCK = re.compile(r"^(?P<file>.+):(?P<a>\d+)\.\d+,(?P<b>\d+)\.\d+ \d+ (?P<count>\d+)$")


class UnsafeXml(ValueError):
    """An XML report that declares entities or a DOCTYPE: refused rather than risk entity expansion."""


def _bad(fmt: str) -> ValueError:
    return ValueError(f"cannot read {fmt} report")


def coveragepy(text: str) -> Lines:
    files: dict[str, dict[str, list[int]]] = json.loads(text)["files"]
    return {
        name: {**{n: 0 for n in data["missing_lines"]}, **{n: 1 for n in data["executed_lines"]}}
        for name, data in files.items()
    }


def gocover(text: str) -> Lines:
    lines: Lines = defaultdict(dict)
    total = 0
    for raw in text.splitlines()[1:]:  # the first line is "mode: ..."
        block = GO_BLOCK.match(raw)
        if block is None:
            raise GauntletError(raw)
        first, last = int(block["a"]), int(block["b"])
        total += last - first + 1
        if last < first or total > MAX_LINES:  # a hostile profile must not make us expand billions of lines
            raise GauntletError(f"implausible block {raw!r}")
        hit = int(block["count"]) > 0
        for n in range(first, last + 1):
            lines[block["file"]][n] = max(lines[block["file"]].get(n, 0), int(hit))
    return dict(lines)


def lcov(text: str) -> Lines:
    lines: Lines = {}
    current: dict[int, int] = {}
    for raw in text.splitlines():
        if raw.startswith("SF:"):
            current = lines.setdefault(raw[3:], {})
        elif raw.startswith("DA:"):
            number, hits, *_ = raw[3:].split(",")
            current[int(number)] = max(current.get(int(number), 0), int(hits))  # any run that reached the line counts
    return lines


def parse_xml(fmt: str, text: str) -> ET.Element:
    if re.search(r"<!(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise UnsafeXml(f"{fmt} report contains a DOCTYPE or entity declaration; refusing to parse it")
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        raise _bad(fmt) from None


def cobertura(text: str) -> Lines:
    root = parse_xml("cobertura", text)
    sources = [(el.text or "").strip() for el in root.iter("source")]
    base = sources[0].rstrip("/") + "/" if len(sources) == 1 and sources[0].startswith("/") else ""
    lines: Lines = {}
    for cls in root.iter("class"):
        name = cls.attrib["filename"]
        target = lines.setdefault(name if name.startswith("/") else base + name, {})
        for line in cls.iter("line"):
            number, hits = int(line.attrib["number"]), int(line.attrib["hits"])
            target[number] = min(target.get(number, hits), hits)  # two classes on one line: the unrun one decides
    return lines


JACOCO_DOCTYPE = '<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">'  # JaCoCo always writes this


def jacoco(text: str) -> Lines:
    lines: Lines = {}
    for package in parse_xml("jacoco", text.replace(JACOCO_DOCTYPE, "", 1)).iter("package"):
        for source in package.iter("sourcefile"):
            target = lines.setdefault(f"{package.attrib['name']}/{source.attrib['name']}", {})
            for line in source.iter("line"):
                covered, missed = int(line.attrib["ci"]), int(line.attrib["mi"])
                if covered + missed:
                    target[int(line.attrib["nr"])] = covered
    return lines


PARSERS: dict[str, Callable[[str], Lines]] = {
    "coveragepy": coveragepy,
    "gocover": gocover,
    "lcov": lcov,
    "cobertura": cobertura,
    "jacoco": jacoco,
}


def parse(fmt: str, text: str) -> Lines:
    if fmt not in PARSERS:
        raise GauntletError(f"unknown coverage format {fmt!r}; expected one of {', '.join(PARSERS)}")
    try:
        return PARSERS[fmt](text)
    except UnsafeXml:
        raise
    except (KeyError, TypeError, AttributeError, ValueError):  # json.JSONDecodeError is a ValueError
        raise _bad(fmt) from None


def _clean_key(key: str) -> tuple[str, bool]:
    """The report path made project-relative, and whether it came from a host root outside the container."""
    foreign_root = key.startswith("/") and not key.startswith("/project/")
    key = key.removeprefix("/project/").lstrip("/")
    if ".." in key.split("/"):
        raise GauntletError(f"{key!r} escapes the project root")
    return key, foreign_root


def _longest_under_prefix(key: str, files: list[str]) -> str | None:
    """The project file that ends `key` when the report put extra leading directories before it."""
    if any(part in SKIP_DIRS for part in key.split("/")):  # never credit a dependency's coverage to our file
        return None
    return max((f for f in files if key.endswith("/" + f)), key=len, default=None)  # mod/cmd/main.go is cmd/main.go


def locate(key: str, files: list[str], prefixed: bool = False) -> str | None:
    """The source file a coverage path names. Reports are relative to different roots, so match by path suffix.

    `prefixed`: the report may put extra leading directories before the project path (a Go module path)."""
    key, foreign_root = _clean_key(key)
    if key in files:
        return key
    shorter = [f for f in files if f.endswith("/" + key)]
    if len(shorter) > 1:
        raise GauntletError(f"coverage path {key!r} matches more than one file: {', '.join(sorted(shorter))}")
    if shorter:
        return shorter[0]
    return _longest_under_prefix(key, files) if prefixed or foreign_root else None
