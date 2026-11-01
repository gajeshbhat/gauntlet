"""coverage.py's JSON report as {file: {line: hit count}}."""

import json

from gauntlet.plugin import Lines


def coveragepy(text: str) -> Lines:
    files: dict[str, dict[str, list[int]]] = json.loads(text)["files"]
    return {
        name: {**{n: 0 for n in data["missing_lines"]}, **{n: 1 for n in data["executed_lines"]}}
        for name, data in files.items()
    }
