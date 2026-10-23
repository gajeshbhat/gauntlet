import pytest

from task import parse_duration


def test_hours_and_minutes() -> None:
    assert parse_duration("1h30m") == 5400


def test_single_units() -> None:
    assert parse_duration("45s") == 45
    assert parse_duration("2d") == 172800


def test_every_unit() -> None:
    assert parse_duration("1d2h3m4s") == 93784


def test_empty_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_duration("")


def test_unknown_unit_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_duration("5x")


def test_units_out_of_order_are_an_error() -> None:
    with pytest.raises(ValueError):
        parse_duration("30m1h")
