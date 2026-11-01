from gauntlet import mutation
from gauntlet.config import Config
from gauntlet.scope import parse


def test_the_python_reader_is_registered() -> None:
    tool = mutation.TOOLS["python"]
    assert tool.read("p.x: killed\np.y: survived\n", parse([]), Config(language="python")).pct == 50.0
    assert tool.artifact == "mutmut-results.txt"
