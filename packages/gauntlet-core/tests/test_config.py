from pathlib import Path

import pytest

from gauntlet.config import Config, Rule, load


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    return path


def test_defaults(tmp_path: Path) -> None:
    cfg = load(write(tmp_path, 'language = "fake"\n'))
    assert cfg == Config(language="fake", crap_max=8, mutation_min=90, layers=(), src=".")


def test_overrides(tmp_path: Path) -> None:
    text = """
language = "fake"
src = "pkg"
[crap]
max = 6
[mutation]
min_score = 95
[layers]
order = ["web", "service", "domain"]
"""
    cfg = load(write(tmp_path, text))
    assert cfg == Config("fake", 6, 95, ("web", "service", "domain"), "pkg", explicit=frozenset({"crap", "mutation"}))


def test_the_mutation_tool_defaults_to_mutmut_and_can_be_chosen(tmp_path: Path) -> None:
    assert load(write(tmp_path, 'language = "fake"\n')).mutation_tool == "mutmut"
    cfg = load(write(tmp_path, 'language = "fake"\n[mutation]\ntool = "other"\n'))
    assert cfg.mutation_tool == "other"
    assert cfg.explicit == frozenset()  # choosing a tool does not claim a score floor


@pytest.mark.parametrize(
    ("value", "message"),
    [('"nope"', "mutation.tool must be one of mutmut, other"), ("5", "tool must be a string")],
)
def test_a_bad_mutation_tool_is_an_error(tmp_path: Path, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load(write(tmp_path, f'language = "fake"\n[mutation]\ntool = {value}\n'))


def test_language_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="language"):
        load(write(tmp_path, "[crap]\nmax = 6\n"))


def test_unsupported_language(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cobol"):
        load(write(tmp_path, 'language = "cobol"\n'))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('language = "fake"\n[crap]\nmax = "8"\n', "max must be an integer between 1 and 1000"),
        ('language = "fake"\n[crap]\nmax = 0\n', "max must be an integer between 1 and 1000"),
        ('language = "fake"\n[crap]\nmax = true\n', "max must be an integer"),
        ('language = "fake"\n[mutation]\nmin_score = 101\n', "min_score must be an integer between 0 and 100"),
        ('language = "fake"\nsrc = 5\n', "src must be a string"),
        ('language = "fake"\n[layers]\norder = "web"\n', "layers.order must be a list"),
        ('language = "fake"\n[layers]\norder = ["web", ""]\n', "layers.order must be a list"),
    ],
)
def test_wrong_types_and_ranges_are_errors(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        load(path)


def test_defaults_are_the_documented_ones(tmp_path: Path) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text('language = "fake"\n')
    cfg = load(path)
    assert (cfg.crap_max, cfg.mutation_min, cfg.src, cfg.layers) == (8, 90, ".", ())


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('src = "x"\n', "gauntlet.toml: 'language' is required"),
        ('language = "cobol"\n', r"unsupported language 'cobol', expected one of fake"),
        ('language = "fake"\nsrc = 3\n', "src must be a string"),
        ('language = "fake"\n[crap]\nmax = 1001\n', "max must be an integer between 1 and 1000"),
        ('language = "fake"\n[mutation]\nmin_score = -1\n', "min_score must be an integer between 0 and 100"),
        ('language = "fake"\n[layers]\nbogus = 1\n', r"unknown key\(s\) bogus in \[layers\]"),
    ],
)
def test_error_messages_are_specific(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=f"^{tmp_path}/{message}" if message.startswith("gauntlet") else message):
        load(path)


def test_boundary_values_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text('language = "fake"\n[crap]\nmax = 1\n[mutation]\nmin_score = 0\n')
    assert (load(path).crap_max, load(path).mutation_min) == (1, 0)
    path.write_text('language = "fake"\n[crap]\nmax = 1000\n[mutation]\nmin_score = 100\n')
    assert (load(path).crap_max, load(path).mutation_min) == (1000, 100)


@pytest.mark.parametrize(
    "text",
    [
        'language = "fake"\nbogus = 1\n',
        'language = "fake"\n[crap]\nmax = 0\n',
        'language = "fake"\n[mutation]\nmin_score = 200\n',
        'language = "fake"\n[layers]\norder = "x"\n',
        'language = "fake"\nsrc = 3\n',
    ],
)
def test_every_error_names_the_file(tmp_path: Path, text: str) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=f"^{path}: "):
        load(path)


def test_roots_and_forbid_rules(tmp_path: Path) -> None:
    text = 'language = "fake"\n[layers]\nroots = ["a/src", "b/src"]\nforbid = ["x -> y", "p.q -> p except p.q, p.r"]\n'
    cfg = load(write(tmp_path, text))
    assert cfg.roots == ("a/src", "b/src")
    assert cfg.forbid == (Rule("x", "y"), Rule("p.q", "p", ("p.q", "p.r")))


@pytest.mark.parametrize("rule", ["x", "x -> ", "x -> y except", "x -> y -> z", "x->y", " -> y"])
def test_bad_forbid_rules_are_rejected(tmp_path: Path, rule: str) -> None:
    text = f'language = "fake"\n[layers]\nforbid = ["{rule}"]\n'
    with pytest.raises(ValueError, match=rf"^{tmp_path}/gauntlet.toml: forbid rule {rule!r} must look like"):
        load(write(tmp_path, text))
