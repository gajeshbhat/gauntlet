from pathlib import Path

import pytest

from gauntlet.config import Config, load


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    return path


def test_defaults(tmp_path: Path) -> None:
    cfg = load(write(tmp_path, 'language = "python"\n'))
    assert cfg == Config(language="python", crap_max=8, mutation_min=90, layers=(), src=".", mutation_dir="")


def test_overrides(tmp_path: Path) -> None:
    text = """
language = "go"
src = "pkg"
[go]
mutation_dir = "lxd/device"
[crap]
max = 6
[mutation]
min_score = 95
[layers]
order = ["web", "service", "domain"]
"""
    cfg = load(write(tmp_path, text))
    assert cfg == Config(
        "go", 6, 95, ("web", "service", "domain"), "pkg", "lxd/device", explicit=frozenset({"crap", "mutation"})
    )


def test_language_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="language"):
        load(write(tmp_path, "[crap]\nmax = 6\n"))


def test_unsupported_language(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rust"):
        load(write(tmp_path, 'language = "rust"\n'))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('language = "python"\n[crap]\nmax = "8"\n', "max must be an integer between 1 and 1000"),
        ('language = "python"\n[crap]\nmax = 0\n', "max must be an integer between 1 and 1000"),
        ('language = "python"\n[crap]\nmax = true\n', "max must be an integer"),
        ('language = "python"\n[mutation]\nmin_score = 101\n', "min_score must be an integer between 0 and 100"),
        ('language = "python"\nsrc = 5\n', "src must be a string"),
        ('language = "python"\n[layers]\norder = "web"\n', "layers.order must be a list"),
        ('language = "python"\n[layers]\norder = ["web", ""]\n', "layers.order must be a list"),
    ],
)
def test_wrong_types_and_ranges_are_errors(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        load(path)


def test_defaults_are_the_documented_ones(tmp_path: Path) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text('language = "go"\n')
    cfg = load(path)
    assert (cfg.crap_max, cfg.mutation_min, cfg.src, cfg.mutation_dir, cfg.layers) == (8, 90, ".", "", ())


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('src = "x"\n', "gauntlet.toml: 'language' is required"),
        ('language = "rust"\n', r"unsupported language 'rust', expected one of \('python', 'go'\)"),
        ('language = "go"\n[go]\nmutation_dir = 3\n', "mutation_dir must be a string"),
        ('language = "go"\n[crap]\nmax = 1001\n', "max must be an integer between 1 and 1000"),
        ('language = "go"\n[mutation]\nmin_score = -1\n', "min_score must be an integer between 0 and 100"),
        ('language = "go"\n[layers]\nbogus = 1\n', r"unknown key\(s\) bogus in \[layers\]"),
    ],
)
def test_error_messages_are_specific(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=f"^{tmp_path}/{message}" if message.startswith("gauntlet") else message):
        load(path)


def test_boundary_values_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text('language = "go"\n[crap]\nmax = 1\n[mutation]\nmin_score = 0\n')
    assert (load(path).crap_max, load(path).mutation_min) == (1, 0)
    path.write_text('language = "go"\n[crap]\nmax = 1000\n[mutation]\nmin_score = 100\n')
    assert (load(path).crap_max, load(path).mutation_min) == (1000, 100)


def test_go_run_settings(tmp_path: Path) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text('language = "go"\n[go]\npackages = ["./a/..."]\nmutate_only = ["x.go"]\n')
    cfg = load(path)
    assert (cfg.packages, cfg.mutate_only) == (("./a/...",), ("x.go",))
    path.write_text('language = "go"\n[go]\npackages = "./a"\n')
    with pytest.raises(ValueError, match="packages must be a list of non-empty strings"):
        load(path)
    path.write_text('language = "go"\n[go]\nmutate_only = [""]\n')
    with pytest.raises(ValueError, match="mutate_only must be a list of non-empty strings"):
        load(path)


@pytest.mark.parametrize(
    "text",
    [
        'language = "python"\nbogus = 1\n',
        'language = "python"\n[crap]\nmax = 0\n',
        'language = "python"\n[mutation]\nmin_score = 200\n',
        'language = "python"\n[layers]\norder = "x"\n',
        'language = "python"\nsrc = 3\n',
        'language = "go"\n[go]\nmutation_dir = 3\n',
        'language = "go"\n[go]\npackages = "x"\n',
        'language = "go"\n[go]\nmutate_only = 5\n',
    ],
)
def test_every_error_names_the_file(tmp_path: Path, text: str) -> None:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=f"^{path}: "):
        load(path)
