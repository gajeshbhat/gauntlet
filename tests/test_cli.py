import pytest

import gauntlet


def test_main_without_commands_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert gauntlet.main() == 2
    assert "no commands yet" in capsys.readouterr().err
