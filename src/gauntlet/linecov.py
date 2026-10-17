"""Line coverage from the formats real tools write, as one shape: {file: {line: hit count}}.

Only executable lines appear in a file's map; a line that is absent is not code that could run.
"""

import json
import re
import xml.etree.ElementTree as ET  # noqa: N817
from collections import defaultdict
from collections.abc import Callable

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
            raise ValueError(raw)
        first, last = int(block["a"]), int(block["b"])
        total += last - first + 1
        if last < first or total > MAX_LINES:  # a hostile profile must not make us expand billions of lines
            raise ValueError(f"implausible block {raw!r}")
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
            current[int(number)] = int(hits)
    return lines


def _xml(fmt: str, text: str) -> ET.Element:
    if re.search(r"<!(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise UnsafeXml(f"{fmt} report contains a DOCTYPE or entity declaration; refusing to parse it")
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        raise _bad(fmt) from None


def cobertura(text: str) -> Lines:
    lines: Lines = {}
    for cls in _xml("cobertura", text).iter("class"):
        target = lines.setdefault(cls.attrib["filename"], {})
        for line in cls.iter("line"):
            target[int(line.attrib["number"])] = int(line.attrib["hits"])
    return lines


def jacoco(text: str) -> Lines:
    lines: Lines = {}
    for package in _xml("jacoco", text).iter("package"):
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
        raise ValueError(f"unknown coverage format {fmt!r}; expected one of {', '.join(PARSERS)}")
    try:
        return PARSERS[fmt](text)
    except UnsafeXml:
        raise
    except (KeyError, TypeError, AttributeError, ValueError):  # json.JSONDecodeError is a ValueError
        raise _bad(fmt) from None


def locate(key: str, files: list[str]) -> str | None:
    """The source file a coverage path names. Reports are relative to different roots, so match by path suffix."""
    key = key.removeprefix("/project/").lstrip("/")
    if ".." in key.split("/"):
        raise ValueError(f"{key!r} escapes the project root")
    found = [f for f in files if f == key or f.endswith("/" + key) or key.endswith("/" + f)]
    if len(found) > 1:
        raise ValueError(f"coverage path {key!r} matches more than one file: {', '.join(sorted(found))}")
    return found[0] if found else None
