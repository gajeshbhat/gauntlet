from pathlib import Path

import pytest
from fakelang import FAKE
from helpers import tree

from gauntlet.arch import Violation, check, check_roots, layer_of
from gauntlet.config import Rule

LAYERS = ("app.web", "app.service", "app.domain")  # outermost first


def test_inward_imports_allowed(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {
            "app/web/views.py": "from app.service import logic\nfrom app.domain import model\n",
            "app/service/logic.py": "from app.domain import model\n",
            "app/domain/model.py": "import json\n",
        },
    )
    assert check(tmp_path, LAYERS, FAKE).violations == []


def test_outward_import_is_a_violation(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {
            "app/domain/model.py": "from app.web import views\n",
            "app/web/views.py": "",
        },
    )
    (v,) = check(tmp_path, LAYERS, FAKE).violations
    assert v == Violation(path="app/domain/model.py", line=1, source="app.domain", target="app.web")


def test_same_layer_import_allowed(tmp_path: Path) -> None:
    tree(tmp_path, {"app/service/a.py": "from app.service import b\n", "app/service/b.py": ""})
    assert check(tmp_path, LAYERS, FAKE).violations == []


def test_modules_outside_layers_are_ignored(tmp_path: Path) -> None:
    tree(tmp_path, {"other/x.py": "from app.web import views\n", "app/domain/m.py": "import other\n"})
    assert check(tmp_path, LAYERS, FAKE).violations == []


def test_no_layers_means_nothing_to_check(tmp_path: Path) -> None:
    tree(tmp_path, {"a.py": "import b\n"})
    assert check(tmp_path, (), FAKE).violations == []


def test_every_import_statement_counts(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {
            "app/domain/m.py": "import app.web.a\nimport app.web.b\n",
            "app/web/a.py": "",
            "app/web/b.py": "",
        },
    )
    assert [v.line for v in check(tmp_path, LAYERS, FAKE).violations] == [1, 2]


def test_files_outside_layers_do_not_stop_the_scan(tmp_path: Path) -> None:
    tree(tmp_path, {"aaa/x.py": "", "app/domain/m.py": "from app.web import v\n", "app/web/v.py": ""})
    assert len(check(tmp_path, LAYERS, FAKE).violations) == 1


def test_package_init_is_named_after_its_package(tmp_path: Path) -> None:
    tree(tmp_path, {"app/domain/__init__.py": "from app.web import v\n", "app/web/v.py": ""})
    (v,) = check(tmp_path, LAYERS, FAKE).violations
    assert v.source == "app.domain"
    assert v.path == "app/domain/__init__.py"


def test_a_single_file_module_is_its_own_layer(tmp_path: Path) -> None:
    tree(tmp_path, {"app/domain.py": "from app.web import v\n", "app/web/v.py": ""})
    (v,) = check(tmp_path, LAYERS, FAKE).violations
    assert v.source == "app.domain"


def test_longest_prefix_wins() -> None:
    layers = ("pkg/device", "pkg/storage", "pkg/device/config")
    assert layer_of("pkg/device/config/x", layers, "/") == 2
    assert layer_of("pkg/device/other", layers, "/") == 0
    assert layer_of("pkg/device", layers, "/") == 0
    assert layer_of("pkg/devices", layers, "/") is None


def test_counts_the_modules_that_belong_to_a_layer(tmp_path: Path) -> None:
    tree(tmp_path, {"app/web/a.py": "", "app/domain/b.py": "", "other/c.py": ""})
    assert check(tmp_path, LAYERS, FAKE).modules == 2


def test_symlinks_leaving_the_root_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    tree(root, {"app/domain/m.py": ""})
    outside = tmp_path / "outside.py"
    outside.write_text("import app.web\n")
    (root / "app" / "domain" / "link.py").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes the project root"):
        check(root, LAYERS, FAKE)


def test_unparseable_layer_module_is_a_clean_error(tmp_path: Path) -> None:
    tree(tmp_path, {"app/domain/m.py": "BROKEN\n"})
    with pytest.raises(ValueError, match=r"cannot analyse app/domain/m\.py"):
        check(tmp_path, LAYERS, FAKE)


def test_oversized_layer_module_is_rejected(tmp_path: Path) -> None:
    tree(tmp_path, {"app/domain/m.py": "x = 1\n" * 10})
    with pytest.raises(ValueError, match="byte limit"):
        check(tmp_path, LAYERS, FAKE, max_bytes=10)


def test_layer_edges_are_collected(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {
            "app/web/v.py": "from app.service import logic\nfrom app.domain import model\n",
            "app/service/logic.py": "from app.domain import model\n",
            "app/domain/model.py": "from app.web import v\nimport json\n",
        },
    )
    assert check(tmp_path, LAYERS, FAKE).edges == frozenset({(0, 1), (0, 2), (1, 2), (2, 0)})


def test_a_forbidden_import_is_a_violation_even_inward(tmp_path: Path) -> None:
    tree(tmp_path, {"app/web/v.py": "from app.domain import model\n", "app/domain/model.py": ""})
    (v,) = check(tmp_path, LAYERS, FAKE, forbid=(Rule("app.web", "app.domain"),)).violations
    assert v == Violation("app/web/v.py", 1, "app.web.v", "app.domain", forbidden=True)


def test_forbid_allows_the_listed_exceptions_and_ignores_other_sources(tmp_path: Path) -> None:
    files = {
        "app/web/v.py": "from app.domain import model\nimport app.service.logic\nimport json\n",
        "app/service/logic.py": "import app.domain.model\n",
        "app/domain/model.py": "",
    }
    tree(tmp_path, files)
    assert (
        check(tmp_path, LAYERS, FAKE, forbid=(Rule("app.web", "app", ("app.domain", "app.service")),)).violations == []
    )
    assert len(check(tmp_path, LAYERS, FAKE, forbid=(Rule("app.web", "app", ("app.domain",)),)).violations) == 1


def test_forbid_flags_the_bare_package_import(tmp_path: Path) -> None:
    tree(tmp_path, {"app/web/v.py": "from app import x\n", "app/domain/m.py": ""})
    assert len(check(tmp_path, LAYERS, FAKE, forbid=(Rule("app.web", "app", ("app.domain",)),)).violations) == 1


def test_check_roots_sums_modules_and_merges_edges(tmp_path: Path) -> None:
    tree(tmp_path, {"a/app/web/v.py": "from app.domain import m\n", "a/app/domain/m.py": ""})
    tree(tmp_path, {"b/app/service/s.py": "from app.domain import m\n"})
    result = check_roots(tmp_path, ("a", "b"), LAYERS, FAKE)
    assert (result.modules, result.edges, result.violations) == (3, frozenset({(0, 2), (1, 2)}), [])


def test_check_roots_reports_violations_in_every_root(tmp_path: Path) -> None:
    tree(tmp_path, {"a/app/domain/m.py": "import app.web\n", "b/app/domain/n.py": "import app.web\n"})
    assert len(check_roots(tmp_path, ("a", "b"), LAYERS, FAKE).violations) == 2


def test_check_roots_refuses_a_root_with_no_modules(tmp_path: Path) -> None:
    tree(tmp_path, {"a/app/web/v.py": "", "b/other.py": ""})
    message = r"^no module under b belongs to any configured layer; check \[layers\] and roots$"
    with pytest.raises(ValueError, match=message):
        check_roots(tmp_path, ("a", "b"), LAYERS, FAKE)


def test_same_layer_imports_are_not_edges(tmp_path: Path) -> None:
    tree(tmp_path, {"app/service/a.py": "from app.service import b\n", "app/service/b.py": ""})
    assert check(tmp_path, LAYERS, FAKE).edges == frozenset()
