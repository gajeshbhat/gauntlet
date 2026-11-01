import pytest

from gauntlet import linecov
from gauntlet.pylang import LANGUAGE

COVERAGEPY = '{"files": {"src/a.py": {"executed_lines": [1, 2], "missing_lines": [4]}}}'


def test_coveragepy() -> None:
    assert linecov.parse(LANGUAGE, COVERAGEPY) == {"src/a.py": {1: 1, 2: 1, 4: 0}}


@pytest.mark.parametrize("text", ["garbage: [[[", '{"files": {"a.py": {}}}'])
def test_malformed_reports_are_clean_errors(text: str) -> None:
    with pytest.raises(ValueError, match="^cannot read coveragepy report$"):
        linecov.parse(LANGUAGE, text)


def test_empty_reports_are_empty_not_errors() -> None:
    assert linecov.parse(LANGUAGE, '{"files": {}}') == {}
