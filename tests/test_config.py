from pathlib import Path

import pytest

from gauntlet.config import Config, load


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    return path


def test_defaults(tmp_path: Path) -> None:
    cfg = load(write(tmp_path, 'language = "python"\n'))
    assert cfg == Config(language="python", crap_max=8, mutation_min=90, layers=())


def test_overrides(tmp_path: Path) -> None:
    text = """
language = "go"
[crap]
max = 6
[mutation]
min_score = 95
[layers]
order = ["web", "service", "domain"]
"""
    cfg = load(write(tmp_path, text))
    assert cfg == Config("go", 6, 95, ("web", "service", "domain"))


def test_language_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="language"):
        load(write(tmp_path, "[crap]\nmax = 6\n"))


def test_unsupported_language(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rust"):
        load(write(tmp_path, 'language = "rust"\n'))
