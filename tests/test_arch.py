from pathlib import Path

from gauntlet.arch import Violation, check, imports

LAYERS = ("app.web", "app.service", "app.domain")  # outermost first


def make(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_imports_absolute_and_from() -> None:
    src = "import a.b\nfrom c.d import e\n"
    assert imports(src, "m", is_package=False) == {"a.b", "c.d", "c.d.e"}


def test_imports_relative_in_module() -> None:
    assert "app.domain.x" in imports("from . import x\n", "app.domain.m", is_package=False)
    assert "app.y" in imports("from .. import y\n", "app.domain.m", is_package=False)


def test_imports_relative_in_package_init() -> None:
    assert "app.domain.x" in imports("from . import x\n", "app.domain", is_package=True)


def test_relative_import_with_module_part() -> None:
    assert "app.domain.z" in imports("from .z import q\n", "app.domain.m", is_package=False)


def test_inward_imports_allowed(tmp_path: Path) -> None:
    make(
        tmp_path,
        {
            "app/web/views.py": "from app.service import logic\nfrom app.domain import model\n",
            "app/service/logic.py": "from app.domain import model\n",
            "app/domain/model.py": "import json\n",
        },
    )
    assert check(tmp_path, LAYERS) == []


def test_outward_import_is_a_violation(tmp_path: Path) -> None:
    make(
        tmp_path,
        {
            "app/domain/model.py": "from app.web import views\n",
            "app/web/views.py": "",
        },
    )
    (v,) = check(tmp_path, LAYERS)
    assert v == Violation(path="app/domain/model.py", line=1, source="app.domain", target="app.web")


def test_same_layer_import_allowed(tmp_path: Path) -> None:
    make(tmp_path, {"app/service/a.py": "from app.service import b\n", "app/service/b.py": ""})
    assert check(tmp_path, LAYERS) == []


def test_modules_outside_layers_are_ignored(tmp_path: Path) -> None:
    make(
        tmp_path, {"other/x.py": "from app.web import views\n", "app/domain/m.py": "import other\n"}
    )
    assert check(tmp_path, LAYERS) == []


def test_no_layers_means_nothing_to_check(tmp_path: Path) -> None:
    make(tmp_path, {"a.py": "import b\n"})
    assert check(tmp_path, ()) == []
