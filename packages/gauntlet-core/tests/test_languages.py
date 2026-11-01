from collections.abc import Iterator
from pathlib import Path

import pytest
from fakelang import FAKE

from gauntlet import languages
from gauntlet.languages import registry as real_registry
from gauntlet.plugin import Language


class Point:
    def __init__(self, name: str, value: Language) -> None:
        self.name, self.value = name, value

    def load(self) -> Language:
        return self.value


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Point]]:
    """The entry points the real registry sees; the registry is rebuilt around each test."""
    points: list[Point] = []

    def entry_points(group: str) -> list[Point]:
        return points if group == "gauntlet.languages" else []

    monkeypatch.setattr(languages, "entry_points", entry_points)
    monkeypatch.setattr(languages, "registry", real_registry)
    real_registry.cache_clear()
    yield points
    real_registry.cache_clear()


def test_the_registry_is_the_installed_entry_points_by_name(installed: list[Point]) -> None:
    installed += [Point("fake", FAKE), Point("other", FAKE)]
    assert real_registry() == {"fake": FAKE, "other": FAKE}
    assert languages.get("other") is FAKE
    assert real_registry() is real_registry()  # built once


def test_two_plugins_with_one_name_are_an_error(installed: list[Point]) -> None:
    installed += [Point("fake", FAKE), Point("fake", FAKE)]
    with pytest.raises(ValueError, match=r"^two plugins register the language 'fake'; uninstall one$"):
        real_registry()


def test_get_names_the_installed_languages_on_a_miss(installed: list[Point]) -> None:
    installed.append(Point("fake", FAKE))
    with pytest.raises(ValueError, match=r"^unsupported language 'cobol', expected one of fake$"):
        languages.get("cobol")


def test_get_says_so_when_no_plugin_is_installed(installed: list[Point]) -> None:
    with pytest.raises(ValueError, match=r"^unsupported language 'python', expected one of none installed$"):
        languages.get("python")


def test_detect_by_marker_files(tmp_path: Path) -> None:
    assert languages.detect(tmp_path) == []
    (tmp_path / "fake.marker").write_text("")
    assert languages.detect(tmp_path) == ["fake"]
    assert languages.detect(tmp_path / "nothing") == []
