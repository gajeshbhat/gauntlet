"""Exclusion comments: the gates must not be dodgeable by hiding code from them."""

import re
from pathlib import Path

from gauntlet import languages
from gauntlet.errors import GauntletError
from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text, source_files
from gauntlet.scope import Scope


def pragmas(root: Path, language: str, scope: Scope) -> list[str]:
    row = languages.get(language)
    pattern = re.compile(row.pragma)
    out: list[str] = []
    for rel in source_files(root, row.suffixes):
        text = read_text(inside(root, rel), MAX_SOURCE_BYTES)
        try:
            comments = row.comments(text)
        except GauntletError as e:
            raise GauntletError(f"cannot analyse {rel}: {e}") from None
        lines = text.splitlines()
        out += [
            f"{rel}:{n}: {lines[n - 1].strip()}"
            for n, comment in comments
            if pattern.search(comment) and scope.contains(rel, n)
        ]
    return out
