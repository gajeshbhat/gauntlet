from pathlib import Path

from gauntlet.arch import Violation, check, imports, layer_of

LAYERS = ("app.web", "app.service", "app.domain")  # outermost first


def make(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_imports_absolute_and_from() -> None:
    src = "import a.b\nfrom c.d import e\n"
    assert imports(src, "") == {"a.b", "c.d", "c.d.e"}


def test_imports_relative_resolve_against_the_package() -> None:
    assert "app.domain.x" in imports("from . import x\n", "app.domain")
    assert "app.y" in imports("from .. import y\n", "app.domain")


def test_relative_import_with_module_part() -> None:
    assert "app.domain.z" in imports("from .z import q\n", "app.domain")


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
    make(tmp_path, {"other/x.py": "from app.web import views\n", "app/domain/m.py": "import other\n"})
    assert check(tmp_path, LAYERS) == []


def test_no_layers_means_nothing_to_check(tmp_path: Path) -> None:
    make(tmp_path, {"a.py": "import b\n"})
    assert check(tmp_path, ()) == []


def test_every_import_statement_counts(tmp_path: Path) -> None:
    make(
        tmp_path,
        {
            "app/domain/m.py": "import app.web.a\nimport app.web.b\n",
            "app/web/a.py": "",
            "app/web/b.py": "",
        },
    )
    assert [v.line for v in check(tmp_path, LAYERS)] == [1, 2]


def test_files_outside_layers_do_not_stop_the_scan(tmp_path: Path) -> None:
    make(tmp_path, {"aaa/x.py": "", "app/domain/m.py": "from app.web import v\n", "app/web/v.py": ""})
    assert len(check(tmp_path, LAYERS)) == 1


def test_package_init_is_named_after_its_package(tmp_path: Path) -> None:
    make(tmp_path, {"app/domain/__init__.py": "from app.web import v\n", "app/web/v.py": ""})
    (v,) = check(tmp_path, LAYERS)
    assert v.source == "app.domain"
    assert v.path == "app/domain/__init__.py"


def test_relative_import_from_init_reaches_outer_layer(tmp_path: Path) -> None:
    make(tmp_path, {"app/domain/__init__.py": "from ..web import v\n", "app/web/v.py": ""})
    assert len(check(tmp_path, LAYERS)) == 1


def test_bare_relative_import_is_resolved() -> None:
    assert imports("from . import x\n", "app") == {"app", "app.x"}


def test_a_single_file_module_is_its_own_layer(tmp_path: Path) -> None:
    make(tmp_path, {"app/domain.py": "from app.web import v\n", "app/web/v.py": ""})
    (v,) = check(tmp_path, LAYERS)
    assert v.source == "app.domain"


def test_relative_import_at_the_source_root() -> None:
    assert imports("from . import x\n", "") == {"x"}


def test_longest_prefix_wins() -> None:
    layers = ("pkg/device", "pkg/storage", "pkg/device/config")
    assert layer_of("pkg/device/config/x", layers, "/") == 2
    assert layer_of("pkg/device/other", layers, "/") == 0
    assert layer_of("pkg/device", layers, "/") == 0
    assert layer_of("pkg/devices", layers, "/") is None
