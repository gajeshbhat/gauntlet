from pathlib import Path

import pytest
from pyhelpers import tree

from gauntlet.arch import check
from gauntlet_python import LANGUAGE
from gauntlet_python.imports import imports

LAYERS = ("app.web", "app.service", "app.domain")  # outermost first


def test_imports_absolute_and_from() -> None:
    src = "import a.b\nfrom c.d import e\n"
    assert imports(src, "") == {"a.b", "c.d", "c.d.e"}


def test_imports_relative_resolve_against_the_package() -> None:
    assert "app.domain.x" in imports("from . import x\n", "app.domain")
    assert "app.y" in imports("from .. import y\n", "app.domain")


def test_relative_import_with_module_part() -> None:
    assert "app.domain.z" in imports("from .z import q\n", "app.domain")


def test_bare_relative_import_is_resolved() -> None:
    assert imports("from . import x\n", "app") == {"app", "app.x"}


def test_relative_import_at_the_source_root() -> None:
    assert imports("from . import x\n", "") == {"x"}


def test_relative_import_from_init_reaches_outer_layer(tmp_path: Path) -> None:
    tree(tmp_path, {"app/domain/__init__.py": "from ..web import v\n", "app/web/v.py": ""})
    assert len(check(tmp_path, LAYERS, LANGUAGE).violations) == 1


def test_unparseable_layer_module_is_a_clean_error(tmp_path: Path) -> None:
    tree(tmp_path, {"app/domain/m.py": "def broken(:\n"})
    with pytest.raises(ValueError, match=r"^cannot analyse app/domain/m\.py: SyntaxError$"):
        check(tmp_path, LAYERS, LANGUAGE)
