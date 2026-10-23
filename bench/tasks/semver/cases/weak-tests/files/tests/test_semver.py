from task import compare


def test_major() -> None:
    assert compare("1.0.0", "2.0.0") == -1


def test_equal() -> None:
    assert compare("1.2.3", "1.2.3") == 0


def test_prerelease_is_lower() -> None:
    assert compare("1.0.0-alpha", "1.0.0") == -1
