import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from gauntlet import policy
from gauntlet.config import Config, load


def cfg(**kw: object) -> Config:
    base = {"language": "python", "explicit": frozenset[str]()}
    return Config(**{**base, **kw})  # type: ignore[arg-type]


def test_defaults_when_no_policy_file() -> None:
    p = policy.load(None)
    assert (p.crap_ceiling, p.mutation_floor, p.max_exclusions) == (8, 90, 10)
    assert not (p.allow_unstamped or p.allow_config_excludes or p.require_pin)


def test_default_path_follows_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert policy.default_path() == tmp_path / "gauntlet" / "policy.toml"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert policy.default_path() == Path.home() / ".config" / "gauntlet" / "policy.toml"


def test_load_reads_values(write_policy: Callable[[str], Path]) -> None:
    p = policy.load(write_policy("crap_ceiling = 6\nmutation_floor = 95\nallow_unstamped = true\n"))
    assert (p.crap_ceiling, p.mutation_floor, p.allow_unstamped) == (6, 95, True)


def test_unknown_keys_are_errors(write_policy: Callable[[str], Path]) -> None:
    with pytest.raises(ValueError, match="unknown key.*crap_ceilng"):
        policy.load(write_policy("crap_ceilng = 6\n"))


def test_wrong_types_are_errors(write_policy: Callable[[str], Path]) -> None:
    with pytest.raises(ValueError, match="crap_ceiling must be an integer"):
        policy.load(write_policy('crap_ceiling = "six"\n'))
    with pytest.raises(ValueError, match="allow_unstamped must be true or false"):
        policy.load(write_policy('allow_unstamped = "yes"\n'))


def test_repo_may_tighten_but_not_weaken() -> None:
    p = policy.Policy(crap_ceiling=8, mutation_floor=90)
    tight = policy.apply(cfg(crap_max=5, mutation_min=95, explicit=frozenset({"crap", "mutation"})), p)
    assert (tight.crap_max, tight.mutation_min) == (5, 95)
    with pytest.raises(ValueError, match=r"crap\.max = 20 is weaker than the policy ceiling 8"):
        policy.apply(cfg(crap_max=20, explicit=frozenset({"crap"})), p)
    with pytest.raises(ValueError, match=r"mutation\.min_score = 50 is weaker than the policy floor 90"):
        policy.apply(cfg(mutation_min=50, explicit=frozenset({"mutation"})), p)


def test_unset_values_take_the_policy_value() -> None:
    p = policy.Policy(crap_ceiling=6, mutation_floor=97)
    eff = policy.apply(cfg(), p)
    assert (eff.crap_max, eff.mutation_min) == (6, 97)


def test_dump_round_trips(write_policy: Callable[[str], Path]) -> None:
    original = policy.Policy(
        crap_ceiling=7,
        mutation_floor=92,
        max_exclusions=3,
        require_pin=True,
        pins={"/a/gauntlet.toml": "sha256:" + "0" * 64},
    )
    path = write_policy(policy.dump(original))
    assert policy.load(path) == original


def make_config(tmp_path: Path, text: str = 'language = "python"\n') -> Path:
    path = tmp_path / "gauntlet.toml"
    path.write_text(text)
    return path


def test_pin_records_and_enforces_the_config_hash(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    pol_path = tmp_path / "policy.toml"
    pinned = policy.pin(policy.load(None), config, pol_path)
    assert pinned.pins[str(config.resolve())] == "sha256:" + hashlib.sha256(config.read_bytes()).hexdigest()
    policy.check_pin(policy.load(pol_path), config)
    config.write_text('language = "python"\n[crap]\nmax = 99\n')
    with pytest.raises(ValueError, match="changed since it was pinned"):
        policy.check_pin(policy.load(pol_path), config)


def test_unpinned_config_is_fine_unless_pins_are_required(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    policy.check_pin(policy.Policy(), config)
    with pytest.raises(ValueError, match="is not pinned"):
        policy.check_pin(policy.Policy(require_pin=True), config)


def test_config_load_rejects_unknown_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown key.*maxx"):
        load(make_config(tmp_path, 'language = "python"\n[crap]\nmaxx = 99\n'))
    with pytest.raises(ValueError, match="unknown key.*bogus"):
        load(make_config(tmp_path, 'language = "python"\nbogus = 1\n'))


def test_config_load_records_what_was_set_explicitly(tmp_path: Path) -> None:
    c = load(make_config(tmp_path, 'language = "go"\n[crap]\nmax = 5\n'))
    assert c.explicit == frozenset({"crap"})


def test_malformed_pins_are_errors(write_policy: Callable[[str], Path]) -> None:
    with pytest.raises(ValueError, match="pins must map"):
        policy.load(write_policy('[pins]\n"/a/gauntlet.toml" = "md5:abc"\n'))
    with pytest.raises(ValueError, match="pins must map"):
        policy.load(write_policy('pins = "x"\n'))


@pytest.mark.parametrize(
    ("line", "field", "value"),
    [
        ("crap_ceiling = 3", "crap_ceiling", 3),
        ("mutation_floor = 99", "mutation_floor", 99),
        ("max_exclusions = 0", "max_exclusions", 0),
        ("allow_config_excludes = true", "allow_config_excludes", True),
        ("allow_unstamped = true", "allow_unstamped", True),
        ("require_pin = true", "require_pin", True),
    ],
)
def test_each_key_sets_only_itself(write_policy: Callable[[str], Path], line: str, field: str, value: object) -> None:
    loaded = policy.load(write_policy(line + "\n"))
    default = policy.Policy()
    for name in (
        "crap_ceiling",
        "mutation_floor",
        "max_exclusions",
        "allow_config_excludes",
        "allow_unstamped",
        "require_pin",
    ):
        expected = value if name == field else getattr(default, name)
        assert getattr(loaded, name) == expected, name


def test_errors_name_the_file(write_policy: Callable[[str], Path]) -> None:
    path = write_policy("crap_ceiling = -1\n")
    with pytest.raises(ValueError, match=f"^{path}: crap_ceiling must be an integer >= 0$"):
        policy.load(path)


def test_negative_and_boolean_integers_are_rejected(write_policy: Callable[[str], Path]) -> None:
    with pytest.raises(ValueError, match="mutation_floor must be an integer"):
        policy.load(write_policy("mutation_floor = true\n"))
    policy.load(write_policy("max_exclusions = 0\n"))


def test_pin_overwrites_the_previous_pin(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    path = tmp_path / "policy.toml"
    first = policy.pin(policy.Policy(), config, path)
    config.write_text('language = "go"\n')
    second = policy.pin(first, config, path)
    assert len(second.pins) == 1
    assert second.pins != first.pins
    assert not path.with_suffix(".tmp").exists()


def test_agent_settings_default_to_disabled(write_policy: Callable[[str], Path]) -> None:
    p = policy.load(write_policy("crap_ceiling = 8\n"))
    assert p.agent_command == ()
    assert (p.agent_env, p.agent_timeout, p.max_rounds) == ((), 1800, 3)


def test_agent_settings_load_and_round_trip(write_policy: Callable[[str], Path]) -> None:
    text = (
        'agent_command = ["claude", "-p", "--dangerously-skip-permissions"]\n'
        'agent_env = ["CLAUDE_CODE_OAUTH_TOKEN"]\nagent_timeout = 900\nmax_rounds = 5\n'
    )
    p = policy.load(write_policy(text))
    assert p.agent_command == ("claude", "-p", "--dangerously-skip-permissions")
    assert (p.agent_env, p.agent_timeout, p.max_rounds) == (("CLAUDE_CODE_OAUTH_TOKEN",), 900, 5)
    assert policy.load(write_policy(policy.dump(p))) == p


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('agent_command = "claude"\n', "agent_command must be a list of non-empty strings"),
        ('agent_command = ["claude", ""]\n', "agent_command must be a list of non-empty strings"),
        ('agent_env = ["bad name"]\n', "agent_env must be a list of environment variable names"),
        ("agent_timeout = 0\n", "agent_timeout must be an integer between 1 and 86400"),
        ("max_rounds = 0\n", "max_rounds must be an integer between 1 and 20"),
        ("max_rounds = 21\n", "max_rounds must be an integer between 1 and 20"),
    ],
)
def test_bad_agent_settings_are_errors(write_policy: Callable[[str], Path], text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        policy.load(write_policy(text))


@pytest.mark.parametrize(
    "text",
    [
        "bogus = 1\n",
        "crap_ceiling = -1\n",
        "allow_unstamped = 1\n",
        "max_rounds = 0\n",
        "agent_command = 3\n",
        'agent_env = ["a b"]\n',
        '[pins]\nx = "md5:1"\n',
    ],
)
def test_every_policy_error_names_the_file(write_policy: Callable[[str], Path], text: str) -> None:
    path = write_policy(text)
    with pytest.raises(ValueError, match=f"^{path}: "):
        policy.load(path)


def test_each_boolean_defaults_to_false_and_each_can_be_set(write_policy: Callable[[str], Path]) -> None:
    for key in ("allow_config_excludes", "allow_unstamped", "require_pin"):
        assert getattr(policy.load(write_policy("max_exclusions = 1\n")), key) is False
        assert getattr(policy.load(write_policy(f"{key} = true\n")), key) is True
